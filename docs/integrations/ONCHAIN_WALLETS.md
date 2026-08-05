# On-chain Wallets

On-chain wallet integration uses public wallet addresses to estimate token balances and portfolio exposure. PureGamma AI must never ask for private keys or seed phrases.

Wallet-derived NAV is an estimate and not financial advice, tax advice, or an official custody statement.

## Current Status

Backend wallet sync is planned. `packages/data/onchain_provider.py` currently contains a placeholder provider.

## Supported Inputs

Allowed:

- Public wallet address.
- Chain selection.
- Optional user label.

Not allowed:

- Private key.
- Seed phrase.
- Hardware wallet recovery phrase.
- Signing request for custody or transfer.

## Sync Flow

Planned flow:

1. User adds a public address.
2. Worker fetches token balances through configured RPC or data provider.
3. System maps token contracts to canonical assets.
4. Pricing engine values positions.
5. NAV marks stale, unsupported, spam, or low-liquidity tokens.

## Configuration

```text
ONCHAIN_RPC_URL=
ETHEREUM_RPC_URL=
BASE_RPC_URL=
ARBITRUM_RPC_URL=
ALCHEMY_API_KEY=
```

## Stablecoins

Stablecoins should use market price when a depeg warning exists. Do not blindly assume every stablecoin is worth $1.

## Privacy

Public addresses can still identify user wealth and activity. Treat addresses as restricted user data.

## Troubleshooting

- RPC rate limit: switch provider or lower sync frequency.
- Unsupported token: add contract mapping.
- Spam token: filter from NAV and mark ignored.
- Stale chain data: show `partial_data=true`.
