import React from 'react';
import { Alert, message } from 'antd';
import { useGetDatasetQuery, useUpdateDatasetMutation } from '../../../../graphql/dataset.generated';
import { Ownership as OwnershipView } from '../../shared/components/legacy/Ownership';
import SchemaView from './schema/Schema';
import { LegacyEntityProfile } from '../../../shared/LegacyEntityProfile';
import { Dataset, EntityType, GlobalTags, GlossaryTerms, SchemaMetadata } from '../../../../types.generated';
import LineageView from './Lineage';
import { Properties as PropertiesView } from '../../shared/components/legacy/Properties';
import DocumentsView from './Documentation';
import DatasetHeader from './DatasetHeader';
import { Message } from '../../../shared/Message';
import TagTermGroup from '../../../shared/tags/TagTermGroup';
import useIsLineageMode from '../../../lineage/utils/useIsLineageMode';
import { useEntityRegistry } from '../../../useEntityRegistry';
import { useGetAuthenticatedUser } from '../../../useGetAuthenticatedUser';
import analytics, { EventType, EntityActionType } from '../../../analytics';
import StatsView from './stats/Stats';

export enum TabType {
    Ownership = 'Ownership',
    Schema = 'Schema',
    Lineage = 'Lineage',
    Properties = 'Properties',
    Documents = 'Documents',
    Queries = 'Queries',
    Stats = 'Stats',
}

const EMPTY_ARR: never[] = [];

/**
 * Responsible for display the Dataset Page
 */
export const DatasetProfile = ({ urn }: { urn: string }): JSX.Element => {
    const entityRegistry = useEntityRegistry();

    const { loading, error, data } = useGetDatasetQuery({ variables: { urn } });

    const user = useGetAuthenticatedUser()?.corpUser;
    const [updateDataset] = useUpdateDatasetMutation({
        refetchQueries: () => ['getDataset'],
        onError: (e) => {
            message.destroy();
            message.error({ content: `Failed to update: \n ${e.message || ''}`, duration: 3 });
        },
    });

    const isLineageMode = useIsLineageMode();

    if (!loading && error) {
        return <Alert type="error" message={error?.message || `Entity failed to load for urn ${urn}`} />;
    }

    const getHeader = (dataset: Dataset) => <DatasetHeader dataset={dataset} updateDataset={updateDataset} />;

    const getTabs = ({
        ownership,
        upstreamLineage,
        downstreamLineage,
        properties,
        datasetProfiles,
        institutionalMemory,
        schema,
        schemaMetadata,
        previousSchemaMetadata,
        editableSchemaMetadata,
        usageStats,
    }: Dataset & { previousSchemaMetadata: SchemaMetadata }) => {
        const tabs = [
            {
                name: TabType.Schema,
                path: TabType.Schema.toLowerCase(),
                content: (
                    <SchemaView
                        urn={urn}
                        schema={schemaMetadata || schema}
                        previousSchemaMetadata={previousSchemaMetadata}
                        usageStats={usageStats}
                        editableSchemaMetadata={editableSchemaMetadata}
                        updateEditableSchema={(update) => {
                            analytics.event({
                                type: EventType.EntityActionEvent,
                                actionType: EntityActionType.UpdateSchemaDescription,
                                entityType: EntityType.Dataset,
                                entityUrn: urn,
                            });
                            return updateDataset({ variables: { input: { urn, editableSchemaMetadata: update } } });
                        }}
                    />
                ),
            },
            {
                name: TabType.Ownership,
                path: TabType.Ownership.toLowerCase(),
                content: (
                    <OwnershipView
                        owners={(ownership && ownership.owners) || EMPTY_ARR}
                        lastModifiedAt={(ownership && ownership.lastModified?.time) || 0}
                        updateOwnership={(update) => {
                            analytics.event({
                                type: EventType.EntityActionEvent,
                                actionType: EntityActionType.UpdateOwnership,
                                entityType: EntityType.Dataset,
                                entityUrn: urn,
                            });
                            return updateDataset({ variables: { input: { urn, ownership: update } } });
                        }}
                    />
                ),
            },
            {
                name: TabType.Lineage,
                path: TabType.Lineage.toLowerCase(),
                content: <LineageView upstreamLineage={upstreamLineage} downstreamLineage={downstreamLineage} />,
            },
            {
                name: TabType.Properties,
                path: TabType.Properties.toLowerCase(),
                content: <PropertiesView properties={properties || EMPTY_ARR} />,
            },
            {
                name: TabType.Documents,
                path: 'docs',
                content: (
                    <DocumentsView
                        authenticatedUserUrn={user?.urn}
                        authenticatedUserUsername={user?.username}
                        documents={institutionalMemory?.elements || EMPTY_ARR}
                        updateDocumentation={(update) => {
                            analytics.event({
                                type: EventType.EntityActionEvent,
                                actionType: EntityActionType.UpdateDocumentation,
                                entityType: EntityType.Dataset,
                                entityUrn: urn,
                            });
                            return updateDataset({ variables: { input: { urn, institutionalMemory: update } } });
                        }}
                    />
                ),
            },
        ];

        if (datasetProfiles && datasetProfiles.length) {
            tabs.unshift({
                name: TabType.Stats,
                path: TabType.Stats.toLowerCase(),
                content: <StatsView urn={urn} profile={datasetProfiles[0]} />,
            });
        }
        return tabs;
    };

    return (
        <>
            {loading && <Message type="loading" content="Loading..." style={{ marginTop: '10%' }} />}
            {data && data.dataset && (
                <LegacyEntityProfile
                    titleLink={`/${entityRegistry.getPathName(
                        EntityType.Dataset,
                    )}/${urn}?is_lineage_mode=${isLineageMode}`}
                    title={data.dataset.name}
                    tags={
                        <TagTermGroup
                            editableTags={data.dataset?.globalTags as GlobalTags}
                            glossaryTerms={data.dataset?.glossaryTerms as GlossaryTerms}
                            canAdd
                            canRemove
                            updateTags={(globalTags) => {
                                analytics.event({
                                    type: EventType.EntityActionEvent,
                                    actionType: EntityActionType.UpdateTags,
                                    entityType: EntityType.Dataset,
                                    entityUrn: urn,
                                });
                                return updateDataset({ variables: { input: { urn, globalTags } } });
                            }}
                        />
                    }
                    tagCardHeader={data.dataset?.glossaryTerms ? 'Tags & Terms' : 'Tags'}
                    tabs={getTabs(data.dataset as Dataset & { previousSchemaMetadata: SchemaMetadata })}
                    header={getHeader(data.dataset as Dataset)}
                    onTabChange={(tab: string) => {
                        analytics.event({
                            type: EventType.EntitySectionViewEvent,
                            entityType: EntityType.Dataset,
                            entityUrn: urn,
                            section: tab,
                        });
                    }}
                />
            )}
        </>
    );
};
