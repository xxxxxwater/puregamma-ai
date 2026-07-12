"""PureGamma trading control-plane domain.

This package never talks to an exchange directly. Runtime commands must pass
through the risk and execution gateways exposed by the isolated runtime.
"""
