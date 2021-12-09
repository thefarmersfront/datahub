package com.linkedin.metadata.systemmetadata;

import com.linkedin.metadata.run.AspectRowSummary;
import com.linkedin.metadata.run.IngestionRunSummary;
import com.linkedin.mxe.SystemMetadata;
import java.util.List;
import javax.annotation.Nullable;


public interface SystemMetadataService {
  /**
   * Deletes a specific aspect from the system metadata service.
   *
   * @param urn the urn of the entity
   * @param aspect the aspect to delete
   */
  void deleteAspect(String urn, String aspect);

  void deleteUrn(String finalOldUrn);

  void insert(@Nullable SystemMetadata systemMetadata, String urn, String aspect);

  List<AspectRowSummary> findByRunId(String runId);

  List<AspectRowSummary> findByRegistry(String registryName, String registryVersion);

  List<IngestionRunSummary> listRuns(
      final Integer pageOffset,
      final Integer pageSize);

  void configure();

  void clear();
}
