from __future__ import annotations

from packages.strategies.btc_momentum import BTCMomentumBreakout
from packages.strategies.eth_btc_rotation import ETHBTCRotation
from packages.strategies.hype_trend import HYPETrendFollowing
from packages.strategies.mstr_btc_proxy import MSTRBTCProxy
from packages.strategies.sol_high_beta import SOLHighBetaRotation
from packages.strategies.strc_event_driven import STRCEventDrivenCreditTrade


STRATEGIES = [
    BTCMomentumBreakout(),
    ETHBTCRotation(),
    SOLHighBetaRotation(),
    HYPETrendFollowing(),
    MSTRBTCProxy(),
    STRCEventDrivenCreditTrade(),
]


def generate_playbooks() -> list[dict]:
    return [strategy.generate().to_dict() for strategy in STRATEGIES]
