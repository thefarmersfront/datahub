import * as React from 'react';
import { CodeSandboxOutlined } from '@ant-design/icons';
import { MlModelGroup, EntityType, SearchResult } from '../../../types.generated';
import { Preview } from './preview/Preview';
import { Entity, IconStyleType, PreviewType } from '../Entity';
import { MLModelGroupProfile } from './profile/MLModelGroupProfile';
import getChildren from '../../lineage/utils/getChildren';
import { Direction } from '../../lineage/types';

/**
 * Definition of the DataHub MlModelGroup entity.
 */
export class MLModelGroupEntity implements Entity<MlModelGroup> {
    type: EntityType = EntityType.MlmodelGroup;

    icon = (fontSize: number, styleType: IconStyleType) => {
        if (styleType === IconStyleType.TAB_VIEW) {
            return <CodeSandboxOutlined style={{ fontSize }} />;
        }

        if (styleType === IconStyleType.HIGHLIGHT) {
            return <CodeSandboxOutlined style={{ fontSize, color: '#9633b9' }} />;
        }

        return (
            <CodeSandboxOutlined
                style={{
                    fontSize,
                    color: '#BFBFBF',
                }}
            />
        );
    };

    isSearchEnabled = () => true;

    isBrowseEnabled = () => true;

    isLineageEnabled = () => true;

    getAutoCompleteFieldName = () => 'name';

    getPathName = () => 'mlModelGroup';

    getCollectionName = () => 'ML Groups';

    renderProfile = (urn: string) => <MLModelGroupProfile urn={urn} />;

    renderPreview = (_: PreviewType, data: MlModelGroup) => {
        return <Preview group={data} />;
    };

    renderSearch = (result: SearchResult) => {
        const data = result.entity as MlModelGroup;
        return <Preview group={data} />;
    };

    getLineageVizConfig = (entity: MlModelGroup) => {
        return {
            urn: entity.urn,
            name: entity.name,
            type: EntityType.MlmodelGroup,
            upstreamChildren: getChildren({ entity, type: EntityType.MlmodelGroup }, Direction.Upstream).map(
                (child) => child.entity.urn,
            ),
            downstreamChildren: getChildren({ entity, type: EntityType.MlmodelGroup }, Direction.Downstream).map(
                (child) => child.entity.urn,
            ),
            icon: entity.platform.info?.logoUrl || undefined,
            platform: entity.platform.name,
        };
    };

    displayName = (data: MlModelGroup) => {
        return data.name;
    };
}
