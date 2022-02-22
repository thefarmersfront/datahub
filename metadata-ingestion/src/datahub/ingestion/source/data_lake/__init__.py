import logging
import os
from datetime import datetime
from math import log10
from typing import Any, Iterable, List, Optional

import parse
import pydeequ
from pydeequ.analyzers import AnalyzerContext
from pyspark.conf import SparkConf
from pyspark.sql import SparkSession
from pyspark.sql.dataframe import DataFrame
from pyspark.sql.types import (
    ArrayType,
    BinaryType,
    BooleanType,
    ByteType,
    DateType,
    DecimalType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    MapType,
    NullType,
    ShortType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from pyspark.sql.utils import AnalysisException

from datahub.emitter.mce_builder import make_data_platform_urn, make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.api.common import PipelineContext
from datahub.ingestion.api.source import Source, SourceReport
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.ingestion.source.aws.s3_util import make_s3_urn
from datahub.ingestion.source.data_lake.config import DataLakeSourceConfig
from datahub.ingestion.source.data_lake.profiling import _SingleTableProfiler
from datahub.ingestion.source.data_lake.report import DataLakeSourceReport
from datahub.metadata.com.linkedin.pegasus2avro.metadata.snapshot import DatasetSnapshot
from datahub.metadata.com.linkedin.pegasus2avro.mxe import MetadataChangeEvent
from datahub.metadata.com.linkedin.pegasus2avro.schema import (
    BooleanTypeClass,
    BytesTypeClass,
    DateTypeClass,
    NullTypeClass,
    NumberTypeClass,
    RecordTypeClass,
    SchemaField,
    SchemaFieldDataType,
    SchemaMetadata,
    StringTypeClass,
    TimeTypeClass,
)
from datahub.metadata.schema_classes import (
    ChangeTypeClass,
    DatasetPropertiesClass,
    MapTypeClass,
    OtherSchemaClass,
)
from datahub.telemetry import stats, telemetry
from datahub.utilities.perf_timer import PerfTimer

# hide annoying debug errors from py4j
logging.getLogger("py4j").setLevel(logging.ERROR)
logger: logging.Logger = logging.getLogger(__name__)


# for a list of all types, see https://spark.apache.org/docs/3.0.3/api/python/_modules/pyspark/sql/types.html
_field_type_mapping = {
    NullType: NullTypeClass,
    StringType: StringTypeClass,
    BinaryType: BytesTypeClass,
    BooleanType: BooleanTypeClass,
    DateType: DateTypeClass,
    TimestampType: TimeTypeClass,
    DecimalType: NumberTypeClass,
    DoubleType: NumberTypeClass,
    FloatType: NumberTypeClass,
    ByteType: BytesTypeClass,
    IntegerType: NumberTypeClass,
    LongType: NumberTypeClass,
    ShortType: NumberTypeClass,
    ArrayType: NullTypeClass,
    MapType: MapTypeClass,
    StructField: RecordTypeClass,
    StructType: RecordTypeClass,
}


def get_column_type(
    report: SourceReport, dataset_name: str, column_type: str
) -> SchemaFieldDataType:
    """
    Maps known Spark types to datahub types
    """
    TypeClass: Any = None

    for field_type, type_class in _field_type_mapping.items():
        if isinstance(column_type, field_type):
            TypeClass = type_class
            break

    # if still not found, report the warning
    if TypeClass is None:

        report.report_warning(
            dataset_name, f"unable to map type {column_type} to metadata schema"
        )
        TypeClass = NullTypeClass

    return SchemaFieldDataType(type=TypeClass())


# flags to emit telemetry for
profiling_flags_to_report = [
    "profile_table_level_only",
    "include_field_null_count",
    "include_field_min_value",
    "include_field_max_value",
    "include_field_mean_value",
    "include_field_median_value",
    "include_field_stddev_value",
    "include_field_quantiles",
    "include_field_distinct_value_frequencies",
    "include_field_histogram",
    "include_field_sample_values",
]


S3_PREFIXES = ["s3://", "s3n://", "s3a://"]


class DataLakeSource(Source):
    source_config: DataLakeSourceConfig
    report: DataLakeSourceReport
    profiling_times_taken: List[float]

    def __init__(self, config: DataLakeSourceConfig, ctx: PipelineContext):
        super().__init__(ctx)
        self.source_config = config
        self.report = DataLakeSourceReport()
        self.profiling_times_taken = []

        telemetry.telemetry_instance.ping(
            "data_lake_profiling",
            "config",
            "enabled",
            1 if config.profiling.enabled else 0,
        )

        if config.profiling.enabled:

            for config_flag in profiling_flags_to_report:
                config_value = getattr(config.profiling, config_flag)
                config_int = (
                    1 if config_value else 0
                )  # convert to int so it can be emitted as a value

                telemetry.telemetry_instance.ping(
                    "data_lake_profiling",
                    "config",
                    config_flag,
                    config_int,
                )

        conf = SparkConf()

        conf.set(
            "spark.jars.packages",
            ",".join(
                [
                    "org.apache.hadoop:hadoop-aws:3.0.3",
                    "org.apache.spark:spark-avro_2.12:3.0.3",
                    pydeequ.deequ_maven_coord,
                ]
            ),
        )

        if self.source_config.aws_config is not None:

            aws_access_key_id = self.source_config.aws_config.aws_access_key_id
            aws_secret_access_key = self.source_config.aws_config.aws_secret_access_key
            aws_session_token = self.source_config.aws_config.aws_session_token

            aws_provided_credentials = [
                aws_access_key_id,
                aws_secret_access_key,
                aws_session_token,
            ]

            if any(x is not None for x in aws_provided_credentials):

                # see https://hadoop.apache.org/docs/r3.0.3/hadoop-aws/tools/hadoop-aws/index.html#Changing_Authentication_Providers
                if all(x is not None for x in aws_provided_credentials):

                    conf.set(
                        "spark.hadoop.fs.s3a.aws.credentials.provider",
                        "org.apache.hadoop.fs.s3a.TemporaryAWSCredentialsProvider",
                    )

                else:
                    conf.set(
                        "spark.hadoop.fs.s3a.aws.credentials.provider",
                        "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
                    )

                if aws_access_key_id is not None:
                    conf.set("spark.hadoop.fs.s3a.access.key", aws_access_key_id)
                if aws_secret_access_key is not None:
                    conf.set(
                        "spark.hadoop.fs.s3a.secret.key",
                        aws_secret_access_key,
                    )
                if aws_session_token is not None:
                    conf.set(
                        "spark.hadoop.fs.s3a.session.token",
                        aws_session_token,
                    )
            else:
                # if no explicit AWS config is provided, use a default AWS credentials provider
                conf.set(
                    "spark.hadoop.fs.s3a.aws.credentials.provider",
                    "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider",
                )

        conf.set("spark.jars.excludes", pydeequ.f2j_maven_coord)
        conf.set("spark.driver.memory", config.spark_driver_memory)

        self.spark = SparkSession.builder.config(conf=conf).getOrCreate()

    @classmethod
    def create(cls, config_dict, ctx):
        config = DataLakeSourceConfig.parse_obj(config_dict)

        return cls(config, ctx)

    def read_file(self, file: str) -> Optional[DataFrame]:

        extension = os.path.splitext(file)[1]

        telemetry.telemetry_instance.ping(
            "data_lake_profiling",
            "file_extension",
            extension,
        )

        if file.endswith(".parquet"):
            df = self.spark.read.parquet(file)
        elif file.endswith(".csv"):
            # see https://sparkbyexamples.com/pyspark/pyspark-read-csv-file-into-dataframe
            df = self.spark.read.csv(
                file,
                header="True",
                inferSchema="True",
                sep=",",
                ignoreLeadingWhiteSpace=True,
                ignoreTrailingWhiteSpace=True,
            )
        elif file.endswith(".tsv"):
            df = self.spark.read.csv(
                file,
                header="True",
                inferSchema="True",
                sep="\t",
                ignoreLeadingWhiteSpace=True,
                ignoreTrailingWhiteSpace=True,
            )
        elif file.endswith(".json"):
            df = self.spark.read.json(file)
        elif file.endswith(".avro"):
            try:
                df = self.spark.read.format("avro").load(file)
            except AnalysisException:
                self.report.report_warning(
                    file,
                    "To ingest avro files, please install the spark-avro package: https://mvnrepository.com/artifact/org.apache.spark/spark-avro_2.12/3.0.3",
                )
                return None

        # TODO: add support for more file types
        # elif file.endswith(".orc"):
        # df = self.spark.read.orc(file)
        else:
            self.report.report_warning(file, f"file {file} has unsupported extension")
            return None

        # replace periods in names because they break PyDeequ
        # see https://mungingdata.com/pyspark/avoid-dots-periods-column-names/
        return df.toDF(*(c.replace(".", "_") for c in df.columns))

    def get_table_schema(
        self, dataframe: DataFrame, file_path: str, table_name: str
    ) -> Iterable[MetadataWorkUnit]:

        data_platform_urn = make_data_platform_urn(self.source_config.platform)
        dataset_urn = make_dataset_urn(
            self.source_config.platform, table_name, self.source_config.env
        )

        dataset_name = os.path.basename(file_path)

        # if no path spec is provided and the file is in S3, then use the S3 path to construct an URN
        if self.source_config.platform == "s3" and self.source_config.path_spec is None:
            dataset_urn = make_s3_urn(file_path, self.source_config.env)

        dataset_snapshot = DatasetSnapshot(
            urn=dataset_urn,
            aspects=[],
        )

        dataset_properties = DatasetPropertiesClass(
            description="",
            customProperties={},
        )
        dataset_snapshot.aspects.append(dataset_properties)

        column_fields = []

        for field in dataframe.schema.fields:

            field = SchemaField(
                fieldPath=field.name,
                type=get_column_type(self.report, dataset_name, field.dataType),
                nativeDataType=str(field.dataType),
                recursive=False,
            )

            column_fields.append(field)

        schema_metadata = SchemaMetadata(
            schemaName=dataset_name,
            platform=data_platform_urn,
            version=0,
            hash="",
            fields=column_fields,
            platformSchema=OtherSchemaClass(rawSchema=""),
        )

        dataset_snapshot.aspects.append(schema_metadata)

        mce = MetadataChangeEvent(proposedSnapshot=dataset_snapshot)
        wu = MetadataWorkUnit(id=file_path, mce=mce)
        self.report.report_workunit(wu)
        yield wu

    def get_table_name(self, relative_path: str) -> str:

        if self.source_config.path_spec is None:
            return relative_path

        def warn():
            self.report.report_warning(
                relative_path,
                f"Unable to determine table name from provided path spec {self.source_config.path_spec} for file {relative_path}",
            )

        name_matches = parse.parse(self.source_config.path_spec, relative_path)

        if name_matches is None:
            warn()
            return relative_path

        if "name" not in name_matches:
            warn()
            return relative_path

        name_matches_dict = name_matches["name"]

        # sort the dictionary of matches by key and take the values
        name_components = [
            v for k, v in sorted(name_matches_dict.items(), key=lambda x: int(x[0]))
        ]

        return ".".join(name_components)

    def ingest_table(
        self, full_path: str, relative_path: str
    ) -> Iterable[MetadataWorkUnit]:

        table_name = self.get_table_name(relative_path)

        table = self.read_file(full_path)

        # if table is not readable, skip
        if table is None:
            return

        # yield the table schema first
        logger.debug(
            f"Ingesting {full_path}: making table schemas {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        yield from self.get_table_schema(table, full_path, table_name)

        # If profiling is not enabled, skip the rest
        if not self.source_config.profiling.enabled:
            return

        with PerfTimer() as timer:
            # init PySpark analysis object
            logger.debug(
                f"Profiling {full_path}: reading file and computing nulls+uniqueness {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            )
            table_profiler = _SingleTableProfiler(
                table,
                self.spark,
                self.source_config.profiling,
                self.report,
                full_path,
            )

            logger.debug(
                f"Profiling {full_path}: preparing profilers to run {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            )
            # instead of computing each profile individually, we run them all in a single analyzer.run() call
            # we use a single call because the analyzer optimizes the number of calls to the underlying profiler
            # since multiple profiles reuse computations, this saves a lot of time
            table_profiler.prepare_table_profiles()

            # compute the profiles
            logger.debug(
                f"Profiling {full_path}: computing profiles {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            )
            analysis_result = table_profiler.analyzer.run()
            analysis_metrics = AnalyzerContext.successMetricsAsDataFrame(
                self.spark, analysis_result
            )

            logger.debug(
                f"Profiling {full_path}: extracting profiles {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            )
            table_profiler.extract_table_profiles(analysis_metrics)

            time_taken = timer.elapsed_seconds()

            logger.info(
                f"Finished profiling {full_path}; took {time_taken:.3f} seconds"
            )

            self.profiling_times_taken.append(time_taken)

        mcp = MetadataChangeProposalWrapper(
            entityType="dataset",
            entityUrn=make_dataset_urn(
                self.source_config.platform, table_name, self.source_config.env
            ),
            changeType=ChangeTypeClass.UPSERT,
            aspectName="datasetProfile",
            aspect=table_profiler.profile,
        )
        wu = MetadataWorkUnit(
            id=f"profile-{self.source_config.platform}-{full_path}", mcp=mcp
        )
        self.report.report_workunit(wu)
        yield wu

    def get_workunits_s3(self) -> Iterable[MetadataWorkUnit]:

        for s3_prefix in S3_PREFIXES:
            if self.source_config.base_path.startswith(s3_prefix):
                plain_base_path = self.source_config.base_path.lstrip(s3_prefix)
                break

        # append a trailing slash if it's not there so prefix filtering works
        if not plain_base_path.endswith("/"):
            plain_base_path = plain_base_path + "/"

        if self.source_config.aws_config is None:
            raise ValueError("AWS config is required for S3 file sources")

        s3 = self.source_config.aws_config.get_s3_resource()
        bucket = s3.Bucket(plain_base_path.split("/")[0])

        unordered_files = []

        for obj in bucket.objects.filter(
            Prefix=plain_base_path.split("/", maxsplit=1)[1]
        ):

            s3_path = f"s3://{obj.bucket_name}/{obj.key}"

            # if table patterns do not allow this file, skip
            if not self.source_config.schema_patterns.allowed(s3_path):
                continue

            # if the file is a directory, skip it
            if obj.key.endswith("/"):
                continue

            file = os.path.basename(obj.key)

            if self.source_config.ignore_dotfiles and file.startswith("."):
                continue

            obj_path = f"s3a://{obj.bucket_name}/{obj.key}"

            unordered_files.append(obj_path)

        for aws_file in sorted(unordered_files):

            relative_path = "./" + aws_file[len(f"s3a://{plain_base_path}") :]

            # pass in the same relative_path as the full_path for S3 files
            yield from self.ingest_table(aws_file, relative_path)

    def get_workunits_local(self) -> Iterable[MetadataWorkUnit]:
        for root, dirs, files in os.walk(self.source_config.base_path):
            for file in sorted(files):

                if self.source_config.ignore_dotfiles and file.startswith("."):
                    continue

                full_path = os.path.join(root, file)

                relative_path = "./" + os.path.relpath(
                    full_path, self.source_config.base_path
                )

                # if table patterns do not allow this file, skip
                if not self.source_config.schema_patterns.allowed(full_path):
                    continue

                yield from self.ingest_table(full_path, relative_path)

    def get_workunits(self) -> Iterable[MetadataWorkUnit]:

        with PerfTimer() as timer:

            # check if file is an s3 object
            if any(
                self.source_config.base_path.startswith(s3_prefix)
                for s3_prefix in S3_PREFIXES
            ):

                yield from self.get_workunits_s3()

            else:
                yield from self.get_workunits_local()

            if not self.source_config.profiling.enabled:
                return

            total_time_taken = timer.elapsed_seconds()

            logger.info(
                f"Profiling {len(self.profiling_times_taken)} table(s) finished in {total_time_taken:.3f} seconds"
            )

            telemetry.telemetry_instance.ping(
                "data_lake_profiling",
                "time_taken_total",
                # bucket by taking floor of log of time taken
                # report the bucket as a label so the count is not collapsed
                str(10 ** int(log10(total_time_taken + 1))),
            )

            if len(self.profiling_times_taken) > 0:

                percentiles = [50, 75, 95, 99]

                percentile_values = stats.calculate_percentiles(
                    self.profiling_times_taken, percentiles
                )

                for percentile in percentiles:
                    telemetry.telemetry_instance.ping(
                        "data_lake_profiling",
                        f"time_taken_p{percentile}",
                        # bucket by taking floor of log of time taken
                        # report the bucket as a label so the count is not collapsed
                        str(10 ** int(log10(percentile_values[percentile] + 1))),
                    )

    def get_report(self):
        return self.report

    def close(self):
        pass
