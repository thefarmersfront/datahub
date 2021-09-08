import { MutationFunctionOptions, FetchResult } from '@apollo/client';

import {
    DataPlatform,
    DatasetEditableProperties,
    DatasetEditablePropertiesUpdate,
    DownstreamEntityRelationships,
    EditableSchemaMetadata,
    EditableSchemaMetadataUpdate,
    EntityType,
    GlobalTags,
    GlobalTagsUpdate,
    GlossaryTerms,
    InstitutionalMemory,
    InstitutionalMemoryUpdate,
    Maybe,
    Ownership,
    OwnershipUpdate,
    SchemaMetadata,
    StringMapEntry,
    UpstreamEntityRelationships,
} from '../../../types.generated';

export type EntityTab = {
    name: string;
    component: React.FunctionComponent;
    shouldHide?: (GenericEntityProperties, T) => boolean;
};

export type EntitySidebarSection = {
    component: React.FunctionComponent;
    shouldHide?: (GenericEntityProperties, T) => boolean;
};

export type GenericEntityProperties = {
    urn?: string;
    name?: Maybe<string>;
    description?: Maybe<string>;
    globalTags?: Maybe<GlobalTags>;
    glossaryTerms?: Maybe<GlossaryTerms>;
    upstreamLineage?: Maybe<UpstreamEntityRelationships>;
    downstreamLineage?: Maybe<DownstreamEntityRelationships>;
    ownership?: Maybe<Ownership>;
    platform?: Maybe<DataPlatform>;
    properties?: Maybe<StringMapEntry[]>;
    institutionalMemory?: Maybe<InstitutionalMemory>;
    schemaMetadata?: Maybe<SchemaMetadata>;
    externalUrl?: Maybe<string>;
    // to indicate something is a Stream, View instead of Dataset... etc
    entityTypeOverride?: Maybe<string>;
    /** Dataset specific- TODO, migrate these out */
    editableSchemaMetadata?: Maybe<EditableSchemaMetadata>;
    editableProperties?: Maybe<DatasetEditableProperties>;
};

export type GenericEntityUpdate = {
    urn: string;
    editableProperties?: Maybe<DatasetEditablePropertiesUpdate>;
    globalTags?: Maybe<GlobalTagsUpdate>;
    ownership?: Maybe<OwnershipUpdate>;
    institutionalMemory?: Maybe<InstitutionalMemoryUpdate>;
    /** Dataset specific- TODO, migrate these out */
    editableSchemaMetadata?: Maybe<EditableSchemaMetadataUpdate>;
};

export type UpdateEntityType<U> = (
    options?:
        | MutationFunctionOptions<
              U,
              {
                  input: GenericEntityUpdate;
              }
          >
        | undefined,
) => Promise<FetchResult<U, Record<string, any>, Record<string, any>>>;

export type EntityContextType = {
    urn: string;
    entityType: EntityType;
    entityData: GenericEntityProperties | null;
    baseEntity: any;
    updateEntity: UpdateEntityType<any>;
    routeToTab: (params: { tabName: string; tabParams?: Record<string, any>; method?: 'push' | 'replace' }) => void;
};
