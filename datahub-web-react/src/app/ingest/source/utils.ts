import YAML from 'yamljs';
import {
    CheckCircleOutlined,
    ClockCircleOutlined,
    CloseCircleOutlined,
    LoadingOutlined,
    WarningOutlined,
} from '@ant-design/icons';
import { ANTD_GRAY, REDESIGN_COLORS } from '../../entity/shared/constants';
import { SOURCE_TEMPLATE_CONFIGS } from './conf/sources';
import { EntityType, FacetMetadata } from '../../../types.generated';
import { capitalizeFirstLetterOnly, pluralize } from '../../shared/textUtil';
import EntityRegistry from '../../entity/EntityRegistry';

export const sourceTypeToIconUrl = (type: string) => {
    return SOURCE_TEMPLATE_CONFIGS.find((config) => config.type === type)?.logoUrl;
};

export const getSourceConfigs = (sourceType: string) => {
    const sourceConfigs = SOURCE_TEMPLATE_CONFIGS.find((configs) => configs.type === sourceType);
    if (!sourceConfigs) {
        throw new Error(`Failed to find source configs with source type ${sourceType}`);
    }
    return sourceConfigs;
};

export const yamlToJson = (yaml: string): string => {
    const obj = YAML.parse(yaml);
    const jsonStr = JSON.stringify(obj);
    return jsonStr;
};

export const jsonToYaml = (json: string): string => {
    const obj = JSON.parse(json);
    const yamlStr = YAML.stringify(obj, 6);
    return yamlStr;
};

export const RUNNING = 'RUNNING';
export const SUCCESS = 'SUCCESS';
export const FAILURE = 'FAILURE';
export const CANCELLED = 'CANCELLED';
export const UP_FOR_RETRY = 'UP_FOR_RETRY';
export const ROLLING_BACK = 'ROLLING_BACK';
export const ROLLED_BACK = 'ROLLED_BACK';
export const ROLLBACK_FAILED = 'ROLLBACK_FAILED';

export const CLI_EXECUTOR_ID = '__datahub_cli_';
export const MANUAL_INGESTION_SOURCE = 'MANUAL_INGESTION_SOURCE';
export const SCHEDULED_INGESTION_SOURCE = 'SCHEDULED_INGESTION_SOURCE';
export const CLI_INGESTION_SOURCE = 'CLI_INGESTION_SOURCE';

export const getExecutionRequestStatusIcon = (status: string) => {
    return (
        (status === RUNNING && LoadingOutlined) ||
        (status === SUCCESS && CheckCircleOutlined) ||
        (status === FAILURE && CloseCircleOutlined) ||
        (status === CANCELLED && CloseCircleOutlined) ||
        (status === UP_FOR_RETRY && ClockCircleOutlined) ||
        (status === ROLLED_BACK && WarningOutlined) ||
        (status === ROLLING_BACK && LoadingOutlined) ||
        (status === ROLLBACK_FAILED && CloseCircleOutlined) ||
        undefined
    );
};

export const getExecutionRequestStatusDisplayText = (status: string) => {
    return (
        (status === RUNNING && 'Running') ||
        (status === SUCCESS && 'Succeeded') ||
        (status === FAILURE && 'Failed') ||
        (status === CANCELLED && 'Cancelled') ||
        (status === UP_FOR_RETRY && 'Up for Retry') ||
        (status === ROLLED_BACK && 'Rolled Back') ||
        (status === ROLLING_BACK && 'Rolling Back') ||
        (status === ROLLBACK_FAILED && 'Rollback Failed') ||
        status
    );
};

export const getExecutionRequestSummaryText = (status: string) => {
    switch (status) {
        case RUNNING:
            return 'Ingestion is running';
        case SUCCESS:
            return 'Ingestion successfully completed';
        case FAILURE:
            return 'Ingestion completed with errors';
        case CANCELLED:
            return 'Ingestion was cancelled';
        case ROLLED_BACK:
            return 'Ingestion was rolled back';
        case ROLLING_BACK:
            return 'Ingestion is in the process of rolling back';
        case ROLLBACK_FAILED:
            return 'Ingestion rollback failed';
        default:
            return 'Ingestion status not recognized';
    }
};

export const getExecutionRequestStatusDisplayColor = (status: string) => {
    return (
        (status === RUNNING && REDESIGN_COLORS.BLUE) ||
        (status === SUCCESS && 'green') ||
        (status === FAILURE && 'red') ||
        (status === UP_FOR_RETRY && 'orange') ||
        (status === CANCELLED && ANTD_GRAY[9]) ||
        (status === ROLLED_BACK && 'orange') ||
        (status === ROLLING_BACK && 'orange') ||
        (status === ROLLBACK_FAILED && 'red') ||
        ANTD_GRAY[7]
    );
};

const ENTITIES_WITH_SUBTYPES = new Set([
    EntityType.Dataset.toLowerCase(),
    EntityType.Container.toLowerCase(),
    EntityType.Notebook.toLowerCase(),
]);

type EntityTypeCount = {
    count: number;
    displayName: string;
};

/**
 * Extract entity type counts to display in the ingestion summary.
 *
 * @param entityTypeFacets the filter facets for entity type.
 * @param subTypeFacets the filter facets for sub types.
 */
export const extractEntityTypeCountsFromFacets = (
    entityRegistry: EntityRegistry,
    entityTypeFacets: FacetMetadata,
    subTypeFacets?: FacetMetadata | null,
): EntityTypeCount[] => {
    const finalCounts: EntityTypeCount[] = [];

    if (subTypeFacets) {
        subTypeFacets.aggregations
            .filter((agg) => agg.count > 0)
            .forEach((agg) =>
                finalCounts.push({
                    count: agg.count,
                    displayName: pluralize(agg.count, capitalizeFirstLetterOnly(agg.value) || ''),
                }),
            );
        entityTypeFacets.aggregations
            .filter((agg) => agg.count > 0)
            .filter((agg) => !ENTITIES_WITH_SUBTYPES.has(agg.value.toLowerCase()))
            .forEach((agg) =>
                finalCounts.push({
                    count: agg.count,
                    displayName: entityRegistry.getCollectionName(agg.value as EntityType),
                }),
            );
    } else {
        // Only use Entity Types- no subtypes.
        entityTypeFacets.aggregations
            .filter((agg) => agg.count > 0)
            .forEach((agg) =>
                finalCounts.push({
                    count: agg.count,
                    displayName: entityRegistry.getCollectionName(agg.value as EntityType),
                }),
            );
    }

    return finalCounts;
};
