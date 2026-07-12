# PureGamma Nautilus Runtime

The production image pins the latest published compatible binary wheel,
`nautilus_trader==1.230.0`, and refuses source builds. The separately cloned
`1.231.0` repository was used for API review only and is not copied or mounted
into this service.

Intel macOS is not supported by the current upstream wheel matrix. On that
platform the service runs Mock Exchange PAPER/SHADOW mode and reports the
native bridge as unavailable. Use the Linux Docker image for native validation.

This service is the isolated execution data plane. The PureGamma API remains the authenticated control plane. The runtime accepts only HMAC-secret-protected internal commands and supports BACKTEST, PAPER, SHADOW, and Mock Exchange in this phase.

It does not accept LIVE orders, withdrawals, transfers, wallet signing, or private keys. A local NautilusTrader checkout is an implementation reference; its source is not copied into PureGamma.

```bash
cd services/nautilus-runtime
python -m pip install -r requirements.txt
NAUTILUS_RUNTIME_SECRET=change-me PYTHONPATH=. uvicorn app.main:app --port 8090
```
