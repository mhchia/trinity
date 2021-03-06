from eth2.beacon.helpers import (
    slot_to_epoch,
)
from eth2.beacon.state_machines.forks.serenity.configs import (
    SERENITY_CONFIG,
)


SLOTS_PER_EPOCH = 4

XIAO_LONG_BAO_CONFIG = SERENITY_CONFIG._replace(
    SLOTS_PER_EPOCH=SLOTS_PER_EPOCH,
    GENESIS_EPOCH=slot_to_epoch(SERENITY_CONFIG.GENESIS_SLOT, SLOTS_PER_EPOCH),
    TARGET_COMMITTEE_SIZE=2,
    SHARD_COUNT=2,
    MIN_ATTESTATION_INCLUSION_DELAY=2,
)
