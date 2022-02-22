package com.linkedin.metadata.graph;

import com.linkedin.common.urn.Urn;
import com.linkedin.metadata.ElasticSearchTestUtils;
import com.linkedin.metadata.ElasticTestUtils;
import com.linkedin.metadata.graph.elastic.ESGraphQueryDAO;
import com.linkedin.metadata.graph.elastic.ESGraphWriteDAO;
import com.linkedin.metadata.graph.elastic.ElasticSearchGraphService;
import com.linkedin.metadata.query.filter.Filter;
import com.linkedin.metadata.query.filter.RelationshipDirection;
import com.linkedin.metadata.query.filter.RelationshipFilter;
import com.linkedin.metadata.search.elasticsearch.ElasticSearchServiceTest;
import com.linkedin.metadata.utils.elasticsearch.IndexConvention;
import com.linkedin.metadata.utils.elasticsearch.IndexConventionImpl;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import javax.annotation.Nonnull;
import org.elasticsearch.client.RestHighLevelClient;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testng.SkipException;
import org.testng.annotations.AfterTest;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.BeforeTest;
import org.testng.annotations.Test;

import static com.linkedin.metadata.DockerTestUtils.checkContainerEngine;
import static com.linkedin.metadata.graph.elastic.ElasticSearchGraphService.INDEX_NAME;
import static org.testng.Assert.assertEquals;


public class ElasticSearchGraphServiceTest extends GraphServiceTestBase {

  private ElasticsearchContainer _elasticsearchContainer;
  private RestHighLevelClient _searchClient;
  private final IndexConvention _indexConvention = new IndexConventionImpl(null);
  private final String _indexName = _indexConvention.getIndexName(INDEX_NAME);
  private ElasticSearchGraphService _client;

  @BeforeTest
  public void setup() {
    _elasticsearchContainer = ElasticTestUtils.getNewElasticsearchContainer();
    checkContainerEngine(_elasticsearchContainer.getDockerClient());
    _elasticsearchContainer.start();
    _searchClient = ElasticTestUtils.buildRestClient(_elasticsearchContainer);
    _client = buildService();
    _client.configure();
  }

  @BeforeMethod
  public void wipe() throws Exception {
    _client.clear();
    syncAfterWrite();
  }

  @Nonnull
  private ElasticSearchGraphService buildService() {
    ESGraphQueryDAO readDAO = new ESGraphQueryDAO(_searchClient, _indexConvention);
    ESGraphWriteDAO writeDAO =
        new ESGraphWriteDAO(_searchClient, _indexConvention, ElasticSearchServiceTest.getBulkProcessor(_searchClient));
    return new ElasticSearchGraphService(_searchClient, _indexConvention, writeDAO, readDAO,
        ElasticSearchServiceTest.getIndexBuilder(_searchClient));
  }

  @AfterTest
  public void tearDown() {
    _elasticsearchContainer.stop();
  }

  @Override
  @Nonnull
  protected GraphService getGraphService() {
    return _client;
  }

  @Override
  protected void syncAfterWrite() throws Exception {
    ElasticSearchTestUtils.syncAfterWrite(_searchClient, _indexName);
  }

  @Override
  protected void assertEqualsAnyOrder(RelatedEntitiesResult actual, RelatedEntitiesResult expected) {
    // https://github.com/linkedin/datahub/issues/3115
    // ElasticSearchGraphService produces duplicates, which is here ignored until fixed
    // actual.count and actual.total not tested due to duplicates
    assertEquals(actual.start, expected.start);
    assertEqualsAnyOrder(actual.entities, expected.entities, RELATED_ENTITY_COMPARATOR);
  }

  @Override
  protected <T> void assertEqualsAnyOrder(List<T> actual, List<T> expected, Comparator<T> comparator) {
    // https://github.com/linkedin/datahub/issues/3115
    // ElasticSearchGraphService produces duplicates, which is here ignored until fixed
    assertEquals(new HashSet<>(actual), new HashSet<>(expected));
  }

  @Override
  public void testFindRelatedEntitiesSourceEntityFilter(Filter sourceEntityFilter, List<String> relationshipTypes,
      RelationshipFilter relationships, List<RelatedEntity> expectedRelatedEntities) throws Exception {
    if (relationships.getDirection() == RelationshipDirection.UNDIRECTED) {
      // https://github.com/linkedin/datahub/issues/3114
      throw new SkipException("ElasticSearchGraphService does not implement UNDIRECTED relationship filter");
    }
    super.testFindRelatedEntitiesSourceEntityFilter(sourceEntityFilter, relationshipTypes, relationships,
        expectedRelatedEntities);
  }

  @Override
  public void testFindRelatedEntitiesDestinationEntityFilter(Filter destinationEntityFilter,
      List<String> relationshipTypes, RelationshipFilter relationships, List<RelatedEntity> expectedRelatedEntities)
      throws Exception {
    if (relationships.getDirection() == RelationshipDirection.UNDIRECTED) {
      // https://github.com/linkedin/datahub/issues/3114
      throw new SkipException("ElasticSearchGraphService does not implement UNDIRECTED relationship filter");
    }
    super.testFindRelatedEntitiesDestinationEntityFilter(destinationEntityFilter, relationshipTypes, relationships,
        expectedRelatedEntities);
  }

  @Override
  public void testFindRelatedEntitiesSourceType(String datasetType, List<String> relationshipTypes,
      RelationshipFilter relationships, List<RelatedEntity> expectedRelatedEntities) throws Exception {
    if (relationships.getDirection() == RelationshipDirection.UNDIRECTED) {
      // https://github.com/linkedin/datahub/issues/3114
      throw new SkipException("ElasticSearchGraphService does not implement UNDIRECTED relationship filter");
    }
    if (datasetType != null && datasetType.isEmpty()) {
      // https://github.com/linkedin/datahub/issues/3116
      throw new SkipException("ElasticSearchGraphService does not support empty source type");
    }
    super.testFindRelatedEntitiesSourceType(datasetType, relationshipTypes, relationships, expectedRelatedEntities);
  }

  @Override
  public void testFindRelatedEntitiesDestinationType(String datasetType, List<String> relationshipTypes,
      RelationshipFilter relationships, List<RelatedEntity> expectedRelatedEntities) throws Exception {
    if (relationships.getDirection() == RelationshipDirection.UNDIRECTED) {
      // https://github.com/linkedin/datahub/issues/3114
      throw new SkipException("ElasticSearchGraphService does not implement UNDIRECTED relationship filter");
    }
    if (datasetType != null && datasetType.isEmpty()) {
      // https://github.com/linkedin/datahub/issues/3116
      throw new SkipException("ElasticSearchGraphService does not support empty destination type");
    }
    super.testFindRelatedEntitiesDestinationType(datasetType, relationshipTypes, relationships,
        expectedRelatedEntities);
  }

  @Test
  @Override
  public void testFindRelatedEntitiesNoRelationshipTypes() {
    // https://github.com/linkedin/datahub/issues/3117
    throw new SkipException("ElasticSearchGraphService does not support empty list of relationship types");
  }

  @Override
  public void testRemoveEdgesFromNode(@Nonnull Urn nodeToRemoveFrom, @Nonnull List<String> relationTypes,
      @Nonnull RelationshipFilter relationshipFilter, List<RelatedEntity> expectedOutgoingRelatedUrnsBeforeRemove,
      List<RelatedEntity> expectedIncomingRelatedUrnsBeforeRemove,
      List<RelatedEntity> expectedOutgoingRelatedUrnsAfterRemove,
      List<RelatedEntity> expectedIncomingRelatedUrnsAfterRemove) throws Exception {
    if (relationshipFilter.getDirection() == RelationshipDirection.UNDIRECTED) {
      // https://github.com/linkedin/datahub/issues/3114
      throw new SkipException("ElasticSearchGraphService does not implement UNDIRECTED relationship filter");
    }
    super.testRemoveEdgesFromNode(nodeToRemoveFrom, relationTypes, relationshipFilter,
        expectedOutgoingRelatedUrnsBeforeRemove, expectedIncomingRelatedUrnsBeforeRemove,
        expectedOutgoingRelatedUrnsAfterRemove, expectedIncomingRelatedUrnsAfterRemove);
  }

  @Test
  @Override
  public void testRemoveEdgesFromNodeNoRelationshipTypes() {
    // https://github.com/linkedin/datahub/issues/3117
    throw new SkipException("ElasticSearchGraphService does not support empty list of relationship types");
  }

  @Test
  @Override
  public void testConcurrentAddEdge() {
    // https://github.com/linkedin/datahub/issues/3124
    throw new SkipException(
        "This test is flaky for ElasticSearchGraphService, ~5% of the runs fail on a race condition");
  }

  @Test
  @Override
  public void testConcurrentRemoveEdgesFromNode() {
    // https://github.com/linkedin/datahub/issues/3118
    throw new SkipException("ElasticSearchGraphService produces duplicates");
  }

  @Test
  @Override
  public void testConcurrentRemoveNodes() {
    // https://github.com/linkedin/datahub/issues/3118
    throw new SkipException("ElasticSearchGraphService produces duplicates");
  }
}
