package datahub.spark.model.dataset;

import com.linkedin.common.urn.DatasetUrn;

public interface SparkDataset {
  DatasetUrn urn();
}
