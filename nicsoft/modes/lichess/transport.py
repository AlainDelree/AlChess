"""
nicsoft/modes/lichess/transport.py — AlChess

Couche de transport réseau du client de partie Lichess (issue #307, étape
L1) : interface minimale (une requête, une lecture de flux ligne par
ligne) injectable dans les tests via un faux transport scénarisé — aucun
test de ce dossier ne doit se connecter au vrai Lichess.

`UrllibTransport` est le transport de production : urllib de la
bibliothèque standard, schéma https vérifié par `ensure_https` avant tout
appel, jeton envoyé uniquement dans l'en-tête d'autorisation (jamais dans
l'URL ni le corps), délai de dix secondes pour les requêtes ordinaires et
délai plus large pour la lecture du flux (la pause entre deux lignes,
lignes vides de maintien incluses, peut dépasser dix secondes).

N'importe jamais nicsoft.web (ARC-001).
"""

import socket
import urllib.error
import urllib.parse
import urllib.request

from nicsoft.utils.net_safety import ensure_https

REQUEST_TIMEOUT_S = 10
# Lichess envoie une ligne vide de maintien toutes les ~9s, mais une partie
# amicale longue (ex. 90+30, réflexions de 15-20 min) peut rester silencieuse
# plus longtemps sans que la connexion soit réellement coupée — 90s de
# tolérance avant de considérer la lecture comme interrompue (issue #309).
STREAM_READ_TIMEOUT_S = 90


def _user_agent() -> str:
    try:
        from importlib.metadata import version
        return f"AlChess/{version('alchess')}"
    except Exception:
        return "AlChess/0.0.0"


class TransportError(Exception):
    """Erreur de transport générique — jamais le jeton dans le message."""


class TransportHTTPError(TransportError):
    """Lichess a répondu avec un code HTTP d'erreur."""

    def __init__(self, status_code: int, body: str = ""):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.body = body


class TransportNetworkError(TransportError):
    """Réseau indisponible (coupure, DNS, connexion refusée, etc.)."""


class TransportTimeoutError(TransportNetworkError):
    """Délai dépassé en attendant une réponse ou une ligne du flux."""


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": _user_agent(),
    }


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


class UrllibTransport:
    """Transport de production. Ne reçoit le jeton qu'en mémoire — jamais
    journalisé, jamais inclus dans une exception."""

    def request(self, method: str, url: str, token: str, fields: dict | None = None) -> bytes:
        ensure_https(url)
        data = urllib.parse.urlencode(fields).encode("utf-8") if fields else None
        req = urllib.request.Request(url, data=data, method=method, headers=_headers(token))
        try:
            # Adresse vérifiée par ensure_https ci-dessus.
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise TransportHTTPError(exc.code, _read_error_body(exc)) from None
        except socket.timeout:
            raise TransportTimeoutError("délai dépassé") from None
        except urllib.error.URLError:
            raise TransportNetworkError("réseau indisponible") from None

    def stream_lines(self, url: str, token: str):
        """Générateur de lignes décodées (lignes vides de maintien incluses).
        S'arrête normalement (fin du générateur) quand Lichess ferme le
        flux ; lève TransportNetworkError/TransportTimeoutError en cas de
        coupure — à l'appelant de décider s'il reprend."""
        ensure_https(url)
        req = urllib.request.Request(url, method="GET", headers=_headers(token))
        try:
            # Adresse vérifiée par ensure_https ci-dessus.
            with urllib.request.urlopen(req, timeout=STREAM_READ_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
                for raw_line in resp:
                    yield raw_line.decode("utf-8", errors="replace").rstrip("\n")
        except urllib.error.HTTPError as exc:
            raise TransportHTTPError(exc.code, _read_error_body(exc)) from None
        except socket.timeout:
            raise TransportTimeoutError("délai dépassé") from None
        except urllib.error.URLError:
            raise TransportNetworkError("réseau indisponible") from None
