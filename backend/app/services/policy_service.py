"""Access policies that depend on the sensitivity level assigned by the AI (or corrected by a person).

| Level        | Share with a whole role          | Who can access                                 |
|--------------|----------------------------------|------------------------------------------------|
| publico      | any role                         | owner, admins, user grants, role grants        |
| interno      | any role                         | owner, admins, user grants, role grants        |
| confidencial | only editor/admin roles          | owner, admins, user grants, editor/admin roles |
| restringido  | not allowed (only named users)   | owner, admins, user grants                     |
"""
from __future__ import annotations

from app.models import Role, SensitivityLevel

POLICIES = [
    {
        "level": SensitivityLevel.PUBLIC.value,
        "role_sharing": "Cualquier rol",
        "access": "Propietario, administradores, usuarios y roles autorizados",
    },
    {
        "level": SensitivityLevel.INTERNAL.value,
        "role_sharing": "Cualquier rol",
        "access": "Propietario, administradores, usuarios y roles autorizados",
    },
    {
        "level": SensitivityLevel.CONFIDENTIAL.value,
        "role_sharing": "Solo roles Editor y Administrador",
        "access": "Propietario, administradores, usuarios autorizados y roles Editor/Administrador",
    },
    {
        "level": SensitivityLevel.RESTRICTED.value,
        "role_sharing": "No permitido: solo usuarios con nombre propio",
        "access": "Propietario, administradores y usuarios autorizados uno por uno",
    },
]


def role_grant_allowed(sensitivity: SensitivityLevel, role: Role) -> bool:
    """Whether a document of this sensitivity may be shared with (or accessed through) a whole role."""
    if sensitivity == SensitivityLevel.RESTRICTED:
        return False
    if sensitivity == SensitivityLevel.CONFIDENTIAL:
        return role in (Role.EDITOR, Role.ADMIN)
    return True


def role_grant_error(sensitivity: SensitivityLevel, role: Role) -> str | None:
    if role_grant_allowed(sensitivity, role):
        return None
    if sensitivity == SensitivityLevel.RESTRICTED:
        return "Los documentos restringidos solo se pueden compartir con usuarios específicos, no con un rol completo."
    return "Los documentos confidenciales no se pueden compartir con todo el rol Lector; compártelo con usuarios específicos."
