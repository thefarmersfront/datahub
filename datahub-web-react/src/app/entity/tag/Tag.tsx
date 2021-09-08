import { TagOutlined, TagFilled } from '@ant-design/icons';
import * as React from 'react';
import { Tag, EntityType, SearchResult } from '../../../types.generated';
import DefaultPreviewCard from '../../preview/DefaultPreviewCard';
import { Entity, IconStyleType, PreviewType } from '../Entity';
import TagProfile from './TagProfile';

/**
 * Definition of the DataHub Tag entity.
 */
export class TagEntity implements Entity<Tag> {
    type: EntityType = EntityType.Tag;

    icon = (fontSize: number, styleType: IconStyleType) => {
        if (styleType === IconStyleType.TAB_VIEW) {
            return <TagFilled style={{ fontSize }} />;
        }

        if (styleType === IconStyleType.HIGHLIGHT) {
            return <TagFilled style={{ fontSize, color: '#B37FEB' }} />;
        }

        return (
            <TagOutlined
                style={{
                    fontSize,
                    color: '#BFBFBF',
                }}
            />
        );
    };

    isSearchEnabled = () => false;

    isBrowseEnabled = () => false;

    isLineageEnabled = () => false;

    getAutoCompleteFieldName = () => 'name';

    getPathName: () => string = () => 'tag';

    getCollectionName: () => string = () => 'Tags';

    renderProfile: (urn: string) => JSX.Element = (_) => <TagProfile />;

    renderPreview = (_: PreviewType, data: Tag) => (
        <DefaultPreviewCard
            description={data.description || ''}
            name={data.name}
            url={`/${this.getPathName()}/${data.urn}`}
        />
    );

    renderSearch = (result: SearchResult) => {
        return this.renderPreview(PreviewType.SEARCH, result.entity as Tag);
    };

    displayName = (data: Tag) => {
        return data.name;
    };
}
