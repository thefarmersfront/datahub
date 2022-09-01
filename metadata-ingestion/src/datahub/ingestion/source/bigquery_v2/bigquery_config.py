import logging
from datetime import timedelta
from typing import Dict, List, Optional

from pydantic import Field, PositiveInt, root_validator

from datahub.configuration.common import AllowDenyPattern, ConfigurationError
from datahub.ingestion.source.usage.usage_common import BaseUsageConfig
from datahub.ingestion.source_config.sql.bigquery import BigQueryConfig

logger = logging.getLogger(__name__)


class BigQueryUsageConfig(BaseUsageConfig):
    query_log_delay: Optional[PositiveInt] = Field(
        default=None,
        description="To account for the possibility that the query event arrives after the read event in the audit logs, we wait for at least query_log_delay additional events to be processed before attempting to resolve BigQuery job information from the logs. If query_log_delay is None, it gets treated as an unlimited delay, which prioritizes correctness at the expense of memory usage.",
    )

    max_query_duration: timedelta = Field(
        default=timedelta(minutes=15),
        description="Correction to pad start_time and end_time with. For handling the case where the read happens within our time range but the query completion event is delayed and happens after the configured end time.",
    )


class BigQueryV2Config(BigQueryConfig):
    project_id_pattern: AllowDenyPattern = Field(
        default=AllowDenyPattern.allow_all(),
        description="Regex patterns for project_id to filter in ingestion.",
    )

    usage: BigQueryUsageConfig = Field(
        default=BigQueryUsageConfig(), description="Usage related configs"
    )
    include_usage_statistics: bool = Field(
        default=True,
        description="Generate usage statistic",
    )

    dataset_pattern: AllowDenyPattern = Field(
        default=AllowDenyPattern.allow_all(),
        description="Regex patterns for dataset to filter in ingestion. Specify regex to only match the schema name. e.g. to match all tables in schema analytics, use the regex 'analytics'",
    )

    debug_include_full_payloads: bool = Field(
        default=False,
        description="Include full payload into events. It is only for debugging and internal use.",
    )

    @root_validator(pre=False)
    def validate_unsupported_configs(cls, values: Dict) -> Dict:
        value = values.get("profiling")
        if value is not None and value.enabled and not value.profile_table_level_only:
            raise ConfigurationError(
                "Only table level profiling is supported. Set `profiling.profile_table_level_only` to True.",
            )
        return values

    @root_validator(pre=False)
    def backward_compatibility_configs_set(cls, values: Dict) -> Dict:

        dataset_pattern = values.get("dataset_pattern")
        schema_pattern = values.get("schema_pattern")
        if (
            dataset_pattern == AllowDenyPattern.allow_all()
            and schema_pattern != AllowDenyPattern.allow_all()
        ):
            logging.warning(
                "dataset_pattern is not set but schema_pattern is set, using schema_pattern as dataset_pattern. schema_pattern will be deprecated, please use dataset_pattern instead."
            )
            values["dataset_pattern"] = schema_pattern
        elif (
            dataset_pattern != AllowDenyPattern.allow_all()
            and schema_pattern != AllowDenyPattern.allow_all()
        ):
            logging.warning(
                "schema_pattern will be ignored in favour of dataset_pattern. schema_pattern will be deprecated, please use dataset_pattern only."
            )

        return values

    def get_table_pattern(self, pattern: List[str]) -> str:
        return "|".join(pattern) if self.table_pattern else ""
