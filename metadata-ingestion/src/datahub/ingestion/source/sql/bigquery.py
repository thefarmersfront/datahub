import collections
import dataclasses
import datetime
import functools
import json
import logging
import os
import re
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from unittest.mock import patch

# This import verifies that the dependencies are available.
import pybigquery  # noqa: F401
import pybigquery.sqlalchemy_bigquery
import pydantic
from dateutil import parser
from google.cloud.bigquery import Client as BigQueryClient
from google.cloud.logging_v2.client import Client as GCPLoggingClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.reflection import Inspector

from datahub.configuration import ConfigModel
from datahub.configuration.common import ConfigurationError
from datahub.configuration.time_window_config import BaseTimeWindowConfig
from datahub.emitter import mce_builder
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.mcp_builder import PlatformKey, gen_containers
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.ingestion.source.sql.sql_common import (
    SQLAlchemyConfig,
    SQLAlchemySource,
    SqlWorkUnit,
    make_sqlalchemy_type,
    register_custom_type,
)
from datahub.ingestion.source.usage.bigquery_usage import (
    BQ_DATE_SHARD_FORMAT,
    BQ_DATETIME_FORMAT,
    AuditLogEntry,
    BigQueryAuditMetadata,
    BigQueryTableRef,
    QueryEvent,
)
from datahub.metadata.com.linkedin.pegasus2avro.metadata.key import DatasetKey
from datahub.metadata.com.linkedin.pegasus2avro.metadata.snapshot import DatasetSnapshot
from datahub.metadata.com.linkedin.pegasus2avro.mxe import MetadataChangeEvent
from datahub.metadata.schema_classes import (
    ChangeTypeClass,
    DatasetLineageTypeClass,
    UpstreamClass,
    UpstreamLineageClass,
)

logger = logging.getLogger(__name__)

BQ_FILTER_RULE_TEMPLATE = """
protoPayload.serviceName="bigquery.googleapis.com"
AND
(
    (
        protoPayload.methodName="jobservice.jobcompleted"
        AND
        protoPayload.serviceData.jobCompletedEvent.eventName="query_job_completed"
        AND
        protoPayload.serviceData.jobCompletedEvent.job.jobStatus.state="DONE"
        AND NOT
        protoPayload.serviceData.jobCompletedEvent.job.jobStatus.error.code:*
        AND
        protoPayload.serviceData.jobCompletedEvent.job.jobStatistics.referencedTables:*
    )
)
AND
timestamp >= "{start_time}"
AND
timestamp < "{end_time}"
""".strip()

BQ_GET_LATEST_PARTITION_TEMPLATE = """
SELECT
    c.table_catalog,
    c.table_schema,
    c.table_name,
    c.column_name,
    c.data_type,
    max(p.partition_id) as partition_id
FROM
    `{project_id}.{schema}.INFORMATION_SCHEMA.COLUMNS` as c
join `{project_id}.{schema}.INFORMATION_SCHEMA.PARTITIONS` as p
on
    c.table_catalog = p.table_catalog
    and c.table_schema = p.table_schema
    and c.table_name = p.table_name
where
    is_partitioning_column = 'YES'
    -- Filter out special partitions (https://cloud.google.com/bigquery/docs/partitioned-tables#date_timestamp_partitioned_tables)
    and p.partition_id not in ('__NULL__', '__UNPARTITIONED__', '__STREAMING_UNPARTITIONED__')
    and STORAGE_TIER='ACTIVE'
    and p.table_name= '{table}'
group by
    c.table_catalog,
    c.table_schema,
    c.table_name,
    c.column_name,
    c.data_type
order by
    c.table_catalog,
    c.table_schema,
    c.table_name,
    c.column_name
""".strip()

SHARDED_TABLE_REGEX = r"^(.+)[_](\d{4}|\d{6}|\d{8}|\d{10})$"

BQ_GET_LATEST_SHARD = """
SELECT SUBSTR(MAX(table_id), LENGTH('{table}_') + 1) as max_shard
FROM `{project_id}.{schema}.__TABLES_SUMMARY__`
WHERE table_id LIKE '{table}%'
""".strip()

# The existing implementation of this method can be found here:
# https://github.com/googleapis/python-bigquery-sqlalchemy/blob/e0f1496c99dd627e0ed04a0c4e89ca5b14611be2/pybigquery/sqlalchemy_bigquery.py#L967-L974.
# The existing implementation does not use the schema parameter and hence
# does not properly resolve the view definitions. As such, we must monkey
# patch the implementation.


def bigquery_audit_metadata_query_template(
    dataset: str, use_date_sharded_tables: bool
) -> str:
    """
    Receives a dataset (with project specified) and returns a query template that is used to query exported
    AuditLogs containing protoPayloads of type BigQueryAuditMetadata.
    :param dataset: the dataset to query against in the form of $PROJECT.$DATASET
    :param use_date_sharded_tables: whether to read from date sharded audit log tables or time partitioned audit log
           tables
    :return: a query template, when supplied start_time and end_time, can be used to query audit logs from BigQuery
    """
    query: str
    if use_date_sharded_tables:
        query = (
            f"""
        SELECT
            timestamp,
            logName,
            insertId,
            protopayload_auditlog AS protoPayload,
            protopayload_auditlog.metadataJson AS metadata
        FROM
            `{dataset}.cloudaudit_googleapis_com_data_access_*`
        """
            + """
        WHERE
            _TABLE_SUFFIX BETWEEN "{start_date}" AND "{end_date}" AND
        """
        )
    else:
        query = f"""
        SELECT
            timestamp,
            logName,
            insertId,
            protopayload_auditlog AS protoPayload,
            protopayload_auditlog.metadataJson AS metadata
        FROM
            `{dataset}.cloudaudit_googleapis_com_data_access`
        WHERE
        """

    audit_log_filter = """    timestamp >= "{start_time}"
    AND timestamp < "{end_time}"
    AND protopayload_auditlog.serviceName="bigquery.googleapis.com"
    AND JSON_EXTRACT_SCALAR(protopayload_auditlog.metadataJson, "$.jobChange.job.jobStatus.jobState") = "DONE"
    AND JSON_EXTRACT(protopayload_auditlog.metadataJson, "$.jobChange.job.jobConfig.queryConfig") IS NOT NULL;
    """

    query = textwrap.dedent(query) + audit_log_filter

    return textwrap.dedent(query)


def get_view_definition(self, connection, view_name, schema=None, **kw):
    view = self._get_table(connection, view_name, schema)
    return view.view_query


pybigquery.sqlalchemy_bigquery.BigQueryDialect.get_view_definition = get_view_definition

# Handle the GEOGRAPHY type. We will temporarily patch the _type_map
# in the get_workunits method of the source.
GEOGRAPHY = make_sqlalchemy_type("GEOGRAPHY")
register_custom_type(GEOGRAPHY)
assert pybigquery.sqlalchemy_bigquery._type_map


class BigQueryCredential(ConfigModel):
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url: str = "https://www.googleapis.com/oauth2/v1/certs"
    type: str = "service_account"
    client_x509_cert_url: Optional[str]

    def __init__(self, **data: Any):
        super().__init__(**data)  # type: ignore
        if not self.client_x509_cert_url:
            self.client_x509_cert_url = (
                f"https://www.googleapis.com/robot/v1/metadata/x509/{self.client_email}"
            )


@dataclass
class BigQueryPartitionColumn:
    table_catalog: str
    table_schema: str
    table_name: str
    column_name: str
    data_type: str
    partition_id: str


def create_credential_temp_file(credential: BigQueryCredential) -> str:
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        cred_json = json.dumps(credential.dict(), indent=4, separators=(",", ": "))
        fp.write(cred_json.encode())
        return fp.name


class BigQueryConfig(BaseTimeWindowConfig, SQLAlchemyConfig):
    scheme: str = "bigquery"
    project_id: Optional[str] = None

    log_page_size: Optional[pydantic.PositiveInt] = 1000
    credential: Optional[BigQueryCredential]
    # extra_client_options, include_table_lineage and max_query_duration are relevant only when computing the lineage.
    extra_client_options: Dict[str, Any] = {}
    include_table_lineage: Optional[bool] = True
    max_query_duration: timedelta = timedelta(minutes=15)

    credentials_path: Optional[str] = None
    bigquery_audit_metadata_datasets: Optional[List[str]] = None
    use_exported_bigquery_audit_metadata: bool = False
    use_date_sharded_audit_log_tables: bool = False

    def __init__(self, **data: Any):
        super().__init__(**data)

        if self.credential:
            self.credentials_path = create_credential_temp_file(self.credential)
            logger.debug(
                f"Creating temporary credential file at {self.credentials_path}"
            )
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path

    def get_sql_alchemy_url(self):
        if self.project_id:
            return f"{self.scheme}://{self.project_id}"
        # When project_id is not set, we will attempt to detect the project ID
        # based on the credentials or environment variables.
        # See https://github.com/mxmzdlv/pybigquery#authentication.
        return f"{self.scheme}://"

    @pydantic.validator("platform_instance")
    def bigquery_doesnt_need_platform_instance(cls, v):
        raise ConfigurationError(
            "BigQuery project ids are globally unique. You do not need to specify a platform instance."
        )

    @pydantic.validator("platform")
    def platform_is_always_bigquery(cls, v):
        return "bigquery"


@dataclasses.dataclass
class ProjectIdKey(PlatformKey):
    project_id: str


@dataclasses.dataclass
class BigQueryDatasetKey(ProjectIdKey):
    dataset_id: str


class BigQuerySource(SQLAlchemySource):
    config: BigQueryConfig
    maximum_shard_ids: Dict[str, str] = dict()
    lineage_metadata: Optional[Dict[str, Set[str]]] = None

    def __init__(self, config, ctx):
        super().__init__(config, ctx, "bigquery")

    def get_db_name(self, inspector: Inspector = None) -> str:
        if self.config.project_id:
            return self.config.project_id
        else:
            return self._get_project_id(inspector)

    def _compute_big_query_lineage(self) -> None:
        if self.config.include_table_lineage:
            if self.config.use_exported_bigquery_audit_metadata:
                self._compute_bigquery_lineage_via_exported_bigquery_audit_metadata()
            else:
                self._compute_bigquery_lineage_via_gcp_logging()

            if self.lineage_metadata is not None:
                logger.info(
                    f"Built lineage map containing {len(self.lineage_metadata)} entries."
                )

    def _compute_bigquery_lineage_via_gcp_logging(self) -> None:
        logger.info("Populating lineage info via GCP audit logs")
        try:
            _clients: List[GCPLoggingClient] = self._make_bigquery_client()
            log_entries: Iterable[AuditLogEntry] = self._get_bigquery_log_entries(
                _clients
            )
            parsed_entries: Iterable[QueryEvent] = self._parse_bigquery_log_entries(
                log_entries
            )
            self.lineage_metadata = self._create_lineage_map(parsed_entries)
        except Exception as e:
            logger.error(
                "Error computing lineage information using GCP logs.",
                e,
            )

    def _compute_bigquery_lineage_via_exported_bigquery_audit_metadata(self) -> None:
        logger.info("Populating lineage info via exported GCP audit logs")
        try:
            _client: BigQueryClient = BigQueryClient(project=self.config.project_id)
            exported_bigquery_audit_metadata: Iterable[
                BigQueryAuditMetadata
            ] = self._get_exported_bigquery_audit_metadata(_client)
            parsed_entries: Iterable[
                QueryEvent
            ] = self._parse_exported_bigquery_audit_metadata(
                exported_bigquery_audit_metadata
            )
            self.lineage_metadata = self._create_lineage_map(parsed_entries)
        except Exception as e:
            logger.error(
                "Error computing lineage information using exported GCP audit logs.",
                e,
            )

    def _make_bigquery_client(self) -> List[GCPLoggingClient]:
        # See https://github.com/googleapis/google-cloud-python/issues/2674 for
        # why we disable gRPC here.
        client_options = self.config.extra_client_options.copy()
        client_options["_use_grpc"] = False
        project_id = self.config.project_id
        if project_id is not None:
            return [GCPLoggingClient(**client_options, project=project_id)]
        else:
            return [GCPLoggingClient(**client_options)]

    def _get_bigquery_log_entries(
        self, clients: List[GCPLoggingClient]
    ) -> Iterable[AuditLogEntry]:
        # Add a buffer to start and end time to account for delays in logging events.
        filter = BQ_FILTER_RULE_TEMPLATE.format(
            start_time=(
                self.config.start_time - self.config.max_query_duration
            ).strftime(BQ_DATETIME_FORMAT),
            end_time=(self.config.end_time + self.config.max_query_duration).strftime(
                BQ_DATETIME_FORMAT
            ),
        )

        assert self.config.log_page_size is not None

        logger.info("Start loading log entries from BigQuery")
        for client in clients:
            entries = client.list_entries(
                filter_=filter, page_size=self.config.log_page_size
            )
            item = 0
            for entry in entries:
                item = item + 1
                if item % self.config.log_page_size == 0:
                    logger.info(f"Read {item} entry from log entries")
                yield entry
        logger.info(f"Finished loading {item} log entries from BigQuery")

    def _get_exported_bigquery_audit_metadata(
        self, bigquery_client: BigQueryClient
    ) -> Iterable[BigQueryAuditMetadata]:
        if self.config.bigquery_audit_metadata_datasets is None:
            return

        start_time: str = (
            self.config.start_time - self.config.max_query_duration
        ).strftime(BQ_DATETIME_FORMAT)
        end_time: str = (
            self.config.end_time + self.config.max_query_duration
        ).strftime(BQ_DATETIME_FORMAT)

        for dataset in self.config.bigquery_audit_metadata_datasets:
            logger.info(
                f"Start loading log entries from BigQueryAuditMetadata in {dataset}"
            )

            query: str
            if self.config.use_date_sharded_audit_log_tables:
                start_date: str = (
                    self.config.start_time - self.config.max_query_duration
                ).strftime(BQ_DATE_SHARD_FORMAT)
                end_date: str = (
                    self.config.end_time + self.config.max_query_duration
                ).strftime(BQ_DATE_SHARD_FORMAT)

                query = bigquery_audit_metadata_query_template(
                    dataset, self.config.use_date_sharded_audit_log_tables
                ).format(
                    start_time=start_time,
                    end_time=end_time,
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                query = bigquery_audit_metadata_query_template(
                    dataset, self.config.use_date_sharded_audit_log_tables
                ).format(start_time=start_time, end_time=end_time)
            query_job = bigquery_client.query(query)

            logger.info(
                f"Finished loading log entries from BigQueryAuditMetadata in {dataset}"
            )

            yield from query_job

    # Currently we only parse JobCompleted events but in future we would want to parse other
    # events to also create field level lineage.
    def _parse_bigquery_log_entries(
        self, entries: Iterable[AuditLogEntry]
    ) -> Iterable[QueryEvent]:
        num_total_log_entries: int = 0
        num_parsed_log_entires: int = 0
        for entry in entries:
            num_total_log_entries += 1
            event: Optional[QueryEvent] = None
            try:
                if QueryEvent.can_parse_entry(entry):
                    event = QueryEvent.from_entry(entry)
                    num_parsed_log_entires += 1
                else:
                    raise RuntimeError("Unable to parse log entry as QueryEvent.")
            except Exception as e:
                self.report.report_failure(
                    f"{entry.log_name}-{entry.insert_id}",
                    f"unable to parse log entry: {entry!r}",
                )
                logger.error("Unable to parse GCP log entry.", e)
            if event is not None:
                yield event
        logger.info(
            f"Parsing BigQuery log entries: Number of log entries scanned={num_total_log_entries}, "
            f"number of log entries successfully parsed={num_parsed_log_entires}"
        )

    def _parse_exported_bigquery_audit_metadata(
        self, audit_metadata_rows: Iterable[BigQueryAuditMetadata]
    ) -> Iterable[QueryEvent]:
        for audit_metadata in audit_metadata_rows:
            event: Optional[QueryEvent] = None
            try:
                if QueryEvent.can_parse_exported_bigquery_audit_metadata(
                    audit_metadata
                ):
                    event = QueryEvent.from_exported_bigquery_audit_metadata(
                        audit_metadata
                    )
                else:
                    raise RuntimeError("Unable to parse log entry as QueryEvent.")
            except Exception as e:
                self.report.report_failure(
                    f"""{audit_metadata["logName"]}-{audit_metadata["insertId"]}""",
                    f"unable to parse log entry: {audit_metadata!r}",
                )
                logger.error("Unable to parse GCP log entry.", e)
            if event is not None:
                yield event

    def _create_lineage_map(self, entries: Iterable[QueryEvent]) -> Dict[str, Set[str]]:
        lineage_map: Dict[str, Set[str]] = collections.defaultdict(set)
        num_entries: int = 0
        num_skipped_entries: int = 0
        for e in entries:
            logger.warning(f"Entry:{e}")
            num_entries += 1
            if e.destinationTable is None or not e.referencedTables:
                num_skipped_entries += 1
                continue
            entry_consumed: bool = False
            for ref_table in e.referencedTables:
                destination_table_str = str(e.destinationTable.remove_extras())
                ref_table_str = str(ref_table.remove_extras())
                if ref_table_str != destination_table_str:
                    lineage_map[destination_table_str].add(ref_table_str)
                    entry_consumed = True
            if not entry_consumed:
                num_skipped_entries += 1
        logger.info(
            f"Creating lineage map: total number of entries={num_entries}, number skipped={num_skipped_entries}."
        )
        return lineage_map

    def get_latest_partition(
        self, schema: str, table: str
    ) -> Optional[BigQueryPartitionColumn]:
        url = self.config.get_sql_alchemy_url()
        engine = create_engine(url, **self.config.options)
        with engine.connect() as con:
            inspector = inspect(con)
            sql = BQ_GET_LATEST_PARTITION_TEMPLATE.format(
                project_id=self.get_db_name(inspector), schema=schema, table=table
            )
            result = con.execute(sql)
            # Bigquery only supports one partition column
            # https://stackoverflow.com/questions/62886213/adding-multiple-partitioned-columns-to-bigquery-table-from-sql-query
            row = result.fetchone()
            if row:
                return BigQueryPartitionColumn(**row)
            return None

    def get_shard_from_table(self, table: str) -> Tuple[str, Optional[str]]:
        match = re.search(SHARDED_TABLE_REGEX, table, re.IGNORECASE)
        if match:
            table_name = match.group(1)
            shard = match.group(2)
            return table_name, shard
        return table, None

    def is_latest_shard(self, project_id: str, schema: str, table: str) -> bool:
        # Getting latest shard from table names
        # https://cloud.google.com/bigquery/docs/partitioned-tables#dt_partition_shard
        table_name, shard = self.get_shard_from_table(table)
        if shard:
            logger.debug(f"{table_name} is sharded and shard id is: {shard}")
            url = self.config.get_sql_alchemy_url()
            engine = create_engine(url, **self.config.options)
            if f"{project_id}.{schema}.{table_name}" not in self.maximum_shard_ids:
                with engine.connect() as con:
                    sql = BQ_GET_LATEST_SHARD.format(
                        project_id=project_id,
                        schema=schema,
                        table=table_name,
                    )

                    result = con.execute(sql)
                    for row in result:
                        max_shard = row["max_shard"]
                        self.maximum_shard_ids[
                            f"{project_id}.{schema}.{table_name}"
                        ] = max_shard

                    logger.debug(f"Max shard for table {table_name} is {max_shard}")

            return (
                self.maximum_shard_ids[f"{project_id}.{schema}.{table_name}"] == shard
            )
        else:
            return True

    def generate_partition_profiler_query(
        self, schema: str, table: str, partition_datetime: Optional[datetime.datetime]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Method returns partition id if table is partitioned or sharded and generate custom partition query for
        partitioned table.
        See more about partitioned tables at https://cloud.google.com/bigquery/docs/partitioned-tables
        """

        partition = self.get_latest_partition(schema, table)
        if partition:
            partition_ts: Union[datetime.datetime, datetime.date]
            if not partition_datetime:
                partition_datetime = parser.parse(partition.partition_id)
            logger.debug(f"{table} is partitioned and partition column is {partition}")
            if partition.data_type in ("TIMESTAMP", "DATETIME"):
                partition_ts = partition_datetime
            elif partition.data_type == "DATE":
                partition_ts = partition_datetime.date()
            else:
                logger.warning(f"Not supported partition type {partition.data_type}")
                return None, None

            custom_sql = """
SELECT
    *
FROM
    `{table_catalog}.{table_schema}.{table_name}`
WHERE
    {column_name} = '{partition_id}'
            """.format(
                table_catalog=partition.table_catalog,
                table_schema=partition.table_schema,
                table_name=partition.table_name,
                column_name=partition.column_name,
                partition_id=partition_ts,
            )

            return (partition.partition_id, custom_sql)
        else:
            # For sharded table we want to get the partition id but not needed to generate custom query
            table, shard = self.get_shard_from_table(table)
            if shard:
                return shard, None
        return None, None

    def is_dataset_eligable_profiling(
        self, dataset_name: str, sql_config: SQLAlchemyConfig
    ) -> bool:
        """
        Method overrides default profiling filter which checks profiling eligibility based on allow-deny pattern.
        This one also don't profile those sharded tables which are not the latest.
        """
        if not super().is_dataset_eligable_profiling(dataset_name, sql_config):
            return False

        (project_id, schema, table) = dataset_name.split(".")
        if not self.is_latest_shard(project_id=project_id, table=table, schema=schema):
            logger.debug(
                f"{dataset_name} is sharded but not the latest shard, skipping..."
            )
            return False
        return True

    @classmethod
    def create(cls, config_dict, ctx):
        config = BigQueryConfig.parse_obj(config_dict)
        return cls(config, ctx)

    # Overriding the get_workunits method to first compute the workunits using the base SQLAlchemySource
    # and then computing lineage information only for those datasets that were ingested. This helps us to
    # maintain a clear separation between SQLAlchemySource and the BigQuerySource. Also, this way we honor
    # that flags like schema and table patterns for lineage computation as well.
    def get_workunits(self) -> Iterable[Union[MetadataWorkUnit, SqlWorkUnit]]:
        # only compute the lineage if the object is none. This is is safety check in case if in future refactoring we
        # end up computing lineage multiple times.
        if self.lineage_metadata is None:
            self._compute_big_query_lineage()
        with patch.dict(
            "pybigquery.sqlalchemy_bigquery._type_map",
            {"GEOGRAPHY": GEOGRAPHY},
            clear=False,
        ):
            for wu in super().get_workunits():
                yield wu
                if (
                    isinstance(wu, SqlWorkUnit)
                    and isinstance(wu.metadata, MetadataChangeEvent)
                    and isinstance(wu.metadata.proposedSnapshot, DatasetSnapshot)
                ):
                    lineage_mcp = self.get_lineage_mcp(wu.metadata.proposedSnapshot.urn)
                    if lineage_mcp is not None:
                        lineage_wu = MetadataWorkUnit(
                            id=f"{self.platform}-{lineage_mcp.entityUrn}-{lineage_mcp.aspectName}",
                            mcp=lineage_mcp,
                        )
                        yield lineage_wu
                        self.report.report_workunit(lineage_wu)

    def get_upstream_tables(
        self, bq_table: str, tables_seen: List[str] = []
    ) -> Set[BigQueryTableRef]:
        upstreams: Set[BigQueryTableRef] = set()
        assert self.lineage_metadata
        for ref_table in self.lineage_metadata[str(bq_table)]:
            upstream_table = BigQueryTableRef.from_string_name(ref_table)
            if upstream_table.is_temporary_table():
                # making sure we don't process a table twice and not get into a recurisve loop
                if ref_table in tables_seen:
                    logger.debug(
                        f"Skipping table {ref_table} because it was seen already"
                    )
                    continue
                tables_seen.append(ref_table)
                if ref_table in self.lineage_metadata:
                    upstreams = upstreams.union(
                        self.get_upstream_tables(ref_table, tables_seen=tables_seen)
                    )
            else:
                upstreams.add(upstream_table)
        return upstreams

    def get_lineage_mcp(
        self, dataset_urn: str
    ) -> Optional[MetadataChangeProposalWrapper]:
        if self.lineage_metadata is None:
            return None
        dataset_key: Optional[DatasetKey] = mce_builder.dataset_urn_to_key(dataset_urn)
        if dataset_key is None:
            return None
        project_id, dataset_name, tablename = dataset_key.name.split(".")
        bq_table = BigQueryTableRef(project_id, dataset_name, tablename)
        if str(bq_table) in self.lineage_metadata:
            upstream_list: List[UpstreamClass] = []
            # Sorting the list of upstream lineage events in order to avoid creating multiple aspects in backend
            # even if the lineage is same but the order is different.
            for upstream_table in sorted(
                self.get_upstream_tables(str(bq_table), tables_seen=[])
            ):
                upstream_table_class = UpstreamClass(
                    mce_builder.make_dataset_urn_with_platform_instance(
                        self.platform,
                        "{project}.{database}.{table}".format(
                            project=upstream_table.project,
                            database=upstream_table.dataset,
                            table=upstream_table.table,
                        ),
                        self.config.platform_instance,
                        self.config.env,
                    ),
                    DatasetLineageTypeClass.TRANSFORMED,
                )
                upstream_list.append(upstream_table_class)

            if upstream_list:
                upstream_lineage = UpstreamLineageClass(upstreams=upstream_list)
                mcp = MetadataChangeProposalWrapper(
                    entityType="dataset",
                    changeType=ChangeTypeClass.UPSERT,
                    entityUrn=dataset_urn,
                    aspectName="upstreamLineage",
                    aspect=upstream_lineage,
                )
                return mcp
        return None

    def prepare_profiler_args(
        self,
        schema: str,
        table: str,
        partition: Optional[str],
        custom_sql: Optional[str] = None,
    ) -> dict:
        self.config: BigQueryConfig
        return dict(
            schema=self.config.project_id,
            table=f"{schema}.{table}",
            partition=partition,
            custom_sql=custom_sql,
        )

    @staticmethod
    @functools.lru_cache()
    def _get_project_id(inspector: Inspector) -> str:
        with inspector.bind.connect() as connection:
            project_id = connection.connection._client.project
            return project_id

    def normalise_dataset_name(self, dataset_name: str) -> str:
        (project_id, schema, table) = dataset_name.split(".")

        trimmed_table_name = (
            BigQueryTableRef.from_spec_obj(
                {"projectId": project_id, "datasetId": schema, "tableId": table}
            )
            .remove_extras()
            .table
        )
        return f"{project_id}.{schema}.{trimmed_table_name}"

    def get_identifier(
        self,
        *,
        schema: str,
        entity: str,
        inspector: Inspector,
        **kwargs: Any,
    ) -> str:
        assert inspector
        project_id = self._get_project_id(inspector)
        table_name = BigQueryTableRef.from_spec_obj(
            {"projectId": project_id, "datasetId": schema, "tableId": entity}
        ).table
        return f"{project_id}.{schema}.{table_name}"

    def standardize_schema_table_names(
        self, schema: str, entity: str
    ) -> Tuple[str, str]:
        # The get_table_names() method of the BigQuery driver returns table names
        # formatted as "<schema>.<table>" as the table name. Since later calls
        # pass both schema and table, schema essentially is passed in twice. As
        # such, one of the schema names is incorrectly interpreted as the
        # project ID. By removing the schema from the table name, we avoid this
        # issue.
        segments = entity.split(".")
        if len(segments) != 2:
            raise ValueError(f"expected table to contain schema name already {entity}")
        if segments[0] != schema:
            raise ValueError(f"schema {schema} does not match table {entity}")
        return segments[0], segments[1]

    def gen_schema_key(self, db_name: str, schema: str) -> PlatformKey:
        return BigQueryDatasetKey(
            project_id=db_name,
            dataset_id=schema,
            platform=self.platform,
            instance=self.config.env,
        )

    def gen_database_key(self, database: str) -> PlatformKey:
        return ProjectIdKey(
            project_id=database,
            platform=self.platform,
            instance=self.config.env,
        )

    def gen_database_containers(self, database: str) -> Iterable[MetadataWorkUnit]:
        domain_urn = self._gen_domain_urn(database)

        database_container_key = self.gen_database_key(database)

        container_workunits = gen_containers(
            container_key=database_container_key,
            name=database,
            sub_types=["Project"],
            domain_urn=domain_urn,
        )

        for wu in container_workunits:
            self.report.report_workunit(wu)
            yield wu

    def gen_schema_containers(
        self, schema: str, db_name: str
    ) -> Iterable[MetadataWorkUnit]:
        schema_container_key = self.gen_schema_key(db_name, schema)

        database_container_key = self.gen_database_key(database=db_name)

        container_workunits = gen_containers(
            schema_container_key,
            schema,
            ["Dataset"],
            database_container_key,
        )

        for wu in container_workunits:
            self.report.report_workunit(wu)
            yield wu

    # We can't use close as it is not called if the ingestion is not successful
    def __del__(self):
        if self.config.credentials_path:
            logger.debug(
                f"Deleting temporary credential file at {self.config.credentials_path}"
            )
            os.unlink(self.config.credentials_path)
