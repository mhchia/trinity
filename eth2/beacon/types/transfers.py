from eth_typing import (
    BLSPubkey,
    BLSSignature,
)
import ssz
from ssz.sedes import (
    bytes48,
    bytes96,
    uint64
)

from eth2.beacon.constants import EMPTY_SIGNATURE

from eth2.beacon.typing import (
    Gwei,
    Slot,
    ValidatorIndex,
)


class Transfer(ssz.Serializable):
    fields = [
        # Sender index
        ('sender', uint64),
        # Recipient index
        ('recipient', uint64),
        # Amount in Gwei
        ('amount', uint64),
        # Fee in Gwei for block proposer
        ('fee', uint64),
        # Inclusion slot
        ('slot', uint64),
        # Sender withdrawal pubkey
        ('pubkey', bytes48),
        # Sender signature
        ('signature', bytes96),
    ]

    def __init__(self,
                 sender: ValidatorIndex=ValidatorIndex(0),
                 recipient: ValidatorIndex=ValidatorIndex(0),
                 amount: Gwei=Gwei(0),
                 fee: Gwei=Gwei(0),
                 slot: Slot=Slot(0),
                 pubkey: BLSPubkey=b'\x00' * 48,
                 signature: BLSSignature=EMPTY_SIGNATURE) -> None:
        super().__init__(
            sender=sender,
            recipient=recipient,
            amount=amount,
            fee=fee,
            slot=slot,
            pubkey=pubkey,
            signature=signature,
        )
