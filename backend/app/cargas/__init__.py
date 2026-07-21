# backend/app/cargas/__init__.py
"""Flujo de carga bancaria (Spec §1.5/§2.2, PRD M7): parsear extracto →
mapear a Transaccion → persistir con dedup idempotente y transacción multi-doc."""
