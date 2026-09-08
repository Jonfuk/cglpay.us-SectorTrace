"""Small, optional client for the Open Jobs release feed.

The package deliberately has no import-time dependency on ``pyarrow`` or on
the Open Jobs service.  The collector is disabled by default and the public
portal never imports this package.
"""

from .commands import OpenJobsClient
from .contract import (
    DEFAULT_CONTRACT,
    DIFF_CONTRACT,
    SNAPSHOT_CONTRACT,
    ArtifactSpec,
    ContractError,
    IntegrityError,
    OpenJobsContract,
    ReleaseMetadata,
    ResourceLimitError,
    SchemaError,
    natural_key,
    parse_release_metadata,
    verify_artifact,
)
from .policy import OpenJobsPolicy, PolicyError
from .reader import (
    DependencyUnavailable,
    ReaderLimits,
    iter_batches,
    iter_records,
    read_parquet,
    read_rows,
)

__all__ = [
    "ArtifactSpec", "ContractError", "DEFAULT_CONTRACT", "DIFF_CONTRACT",
    "DependencyUnavailable", "IntegrityError", "OpenJobsClient",
    "OpenJobsContract", "OpenJobsPolicy", "PolicyError", "ReaderLimits",
    "ReleaseMetadata", "ResourceLimitError", "SNAPSHOT_CONTRACT", "SchemaError",
    "iter_batches", "iter_records", "natural_key", "parse_release_metadata",
    "read_parquet", "read_rows", "verify_artifact",
]
