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

import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

from nicsoft.utils.net_safety import ensure_https

logger = logging.getLogger("niclink.lichess")

# Issue #329 : corps de réponse journalisé tronqué à ~500 caractères
# (Lichess y explique la cause du refus) — jamais le jeton (absent du
# corps/de l'URL, seulement dans l'en-tête Authorization, jamais journalisé
# ici ni ailleurs dans ce module).
_LOG_BODY_TRUNCATE = 500

REQUEST_TIMEOUT_S = 10
# Lichess envoie une ligne vide de maintien toutes les ~9s, mais une partie
# amicale longue (ex. 90+30, réflexions de 15-20 min) peut rester silencieuse
# plus longtemps sans que la connexion soit réellement coupée — 90s de
# tolérance avant de considérer la lecture comme interrompue (issue #309).
# Reste utilisé pour les flux SANS maintien de connexion régulier établi
# (recherche d'adversaire et flux général d'évènements, seek.py —
# `open_stream`/`StreamHandle` ci-dessous) : non concerné par #392, point
# 3e, faute de preuve qu'un seuil plus court y soit sûr (pas de fausse
# reconnexion).
STREAM_READ_TIMEOUT_S = 90
# Issue #392, point 3e (étude #391, point 3) : seuil dédié au flux de
# PARTIE (`stream_lines`, utilisé uniquement par
# GameClient.stream_game) — 90s laissait passer une coupure réelle de
# 25-37s SANS LA MOINDRE EXCEPTION (essai réel du 26/11/2026 : 2.c4/3.e4
# envoyés et acceptés par Lichess, mais jamais affichés, position locale
# figée 4 demi-coups, blocage total jusqu'à abandon). Valeur retenue : 20s.
# Justification (aucune documentation PRIMAIRE officielle trouvée donnant
# l'intervalle exact — recherche faite le 26/11/2026) : le commentaire
# ci-dessus (~9s, déjà estimé par #309) est corroboré par plusieurs sources
# communautaires indépendantes (dépôts BotLi et lichess-bot, miroir
# mintlify/deepwiki de la doc officielle) qui convergent sur un maintien de
# connexion Lichess de l'ordre de 7 à 9s pour les flux NDJSON (évènements
# et partie) — jamais confirmé par la spécification officielle elle-même.
# 20s laisse une marge large (plus du double de l'intervalle estimé) pour
# absorber un aller-retour réseau lent ou quelques maintiens manqués sans
# déclencher de fausse reconnexion, tout en détectant une coupure réelle
# bien avant l'ancien seuil et avant même la durée observée le 26/11/2026.
GAME_STREAM_READ_TIMEOUT_S = 20


def _user_agent() -> str:
    try:
        from importlib.metadata import version
        return f"AlChess/{version('alchess')}"
    except Exception:
        return "AlChess/0.0.0"


class TransportError(Exception):
    """Erreur de transport générique — jamais le jeton dans le message."""


class TransportHTTPError(TransportError):
    """Lichess a répondu avec un code HTTP d'erreur. `retry_after_s` (issue
    #329) : valeur de l'en-tête Retry-After renvoyé par Lichess (429
    notamment), None s'il est absent ou illisible — jamais une valeur
    inventée ici (c'est à l'appelant de choisir un repli, voir errors.py)."""

    def __init__(self, status_code: int, body: str = "", retry_after_s: int | None = None):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.body = body
        self.retry_after_s = retry_after_s


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


def _parse_retry_after(exc: urllib.error.HTTPError) -> int | None:
    headers = getattr(exc, "headers", None)
    value = headers.get("Retry-After") if headers is not None else None
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _log_http_error(method: str, url: str, exc: urllib.error.HTTPError, body: str, retry_after_s: int | None) -> None:
    """Journal général (issue #329, point 1) — méthode et chemin SANS
    paramètres (jamais de jeton dans l'un ou l'autre : le jeton n'est
    envoyé que dans l'en-tête Authorization, jamais journalisé), code de
    réponse, Retry-After s'il existe, corps tronqué à ~500 caractères.
    Appelé pour TOUS les appels passant par UrllibTransport, la recherche
    d'adversaire (open_stream) comme les autres (request/stream_lines)."""
    path = urllib.parse.urlparse(url).path
    truncated = body[:_LOG_BODY_TRUNCATE].replace("\n", " ").replace("\r", " ").strip()
    retry_part = f", Retry-After={retry_after_s}s" if retry_after_s is not None else ""
    logger.warning(
        "Lichess : erreur HTTP %s %s -> %s%s — corps : %s",
        method, path, exc.code, retry_part, truncated or "(vide)",
    )


def _wrap_http_error(method: str, url: str, exc: urllib.error.HTTPError) -> TransportHTTPError:
    """Lit le corps, journalise (journal général — point 1), puis retourne
    l'exception typée portant le même détail pour l'appelant (journal de
    partie dédié, choix du message affiché)."""
    body = _read_error_body(exc)
    retry_after_s = _parse_retry_after(exc)
    _log_http_error(method, url, exc, body, retry_after_s)
    return TransportHTTPError(exc.code, body, retry_after_s)


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
            raise _wrap_http_error(method, url, exc) from None
        except socket.timeout:
            raise TransportTimeoutError("délai dépassé") from None
        except urllib.error.URLError:
            raise TransportNetworkError("réseau indisponible") from None

    def stream_lines(self, url: str, token: str):
        """Générateur de lignes décodées (lignes vides de maintien incluses).
        S'arrête normalement (fin du générateur) quand Lichess ferme le
        flux ; lève TransportNetworkError/TransportTimeoutError en cas de
        coupure — à l'appelant de décider s'il reprend. Seul appelant :
        GameClient.stream_game()/peek_game_full() (flux de PARTIE) — seuil
        dédié GAME_STREAM_READ_TIMEOUT_S (issue #392, point 3e), distinct
        de STREAM_READ_TIMEOUT_S (recherche/évènements, open_stream)."""
        ensure_https(url)
        req = urllib.request.Request(url, method="GET", headers=_headers(token))
        try:
            # Adresse vérifiée par ensure_https ci-dessus.
            with urllib.request.urlopen(req, timeout=GAME_STREAM_READ_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
                for raw_line in resp:
                    yield raw_line.decode("utf-8", errors="replace").rstrip("\n")
        except urllib.error.HTTPError as exc:
            raise _wrap_http_error("GET", url, exc) from None
        except socket.timeout:
            raise TransportTimeoutError("délai dépassé") from None
        except urllib.error.URLError:
            raise TransportNetworkError("réseau indisponible") from None

    def open_stream(self, method: str, url: str, token: str, fields: dict | None = None) -> "StreamHandle":
        """Ouvre un flux (GET ou POST) et retourne une poignée annulable
        (issue #327, points 2/3 : recherche d'adversaire humain, board/seek
        ET le flux général d'évènements /api/stream/event, ouverts en
        parallèle, chacun dans son propre fil de lecture — voir
        nicsoft/modes/lichess/seek.py). Contrairement à `stream_lines`
        ci-dessus, la réponse n'est pas consommée ici : l'appelant lit via
        `StreamHandle.lines()` depuis un fil dédié et peut annuler
        l'opération depuis un AUTRE fil en appelant `StreamHandle.close()`,
        ce qui ferme la connexion TCP sous-jacente — c'est précisément ainsi
        que Lichess annule une recherche d'adversaire côté serveur (doc
        officielle lichess-org/api, doc/specs/tags/board/api-board-seek.yaml,
        lue le 14/11/2026 : « If the client closes the connection, the seek
        is canceled »)."""
        ensure_https(url)
        data = urllib.parse.urlencode(fields).encode("utf-8") if fields else None
        req = urllib.request.Request(url, data=data, method=method, headers=_headers(token))
        try:
            # Adresse vérifiée par ensure_https ci-dessus.
            resp = urllib.request.urlopen(req, timeout=STREAM_READ_TIMEOUT_S)  # noqa: S310  # nosec B310
        except urllib.error.HTTPError as exc:
            raise _wrap_http_error(method, url, exc) from None
        except socket.timeout:
            raise TransportTimeoutError("délai dépassé") from None
        except urllib.error.URLError:
            raise TransportNetworkError("réseau indisponible") from None
        return StreamHandle(resp)


class StreamHandle:
    """Poignée d'un flux ouvert par `UrllibTransport.open_stream` — voir sa
    documentation pour le détail de l'annulation. `lines()` est un
    générateur à usage unique ; `close()` est idempotent et sans effet si
    le flux est déjà terminé (jamais d'exception à l'annulation, même
    appelée deux fois ou après la fin naturelle du flux)."""

    def __init__(self, response):
        self._response = response
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._shutdown_underlying_socket()
        try:
            self._response.close()
        except Exception:
            pass

    def _shutdown_underlying_socket(self) -> None:
        """Coupe la connexion TCP sous-jacente AVANT la fermeture ci-dessus
        (issue #383, point 2) — essai réel : un simple `self._response.close()`
        appelé depuis un AUTRE fil pendant qu'un fil de lecture est bloqué
        dans `lines()` ne réveille PAS ce fil ; pire, `close()` lui-même se
        bloque alors jusqu'à l'arrivée naturelle de données suivantes (ou
        jamais, si aucune ne vient) — le verrou interne du tampon
        (`io.BufferedReader`) est partagé entre lecture et fermeture. Seul
        `socket.shutdown(SHUT_RDWR)` sur le socket brut, qui n'a besoin
        d'aucun verrou de ce tampon, fait immédiatement échouer le `recv()`
        bloquant dans l'autre fil, sur Linux comme sur Windows (sémantique
        Winsock identique pour `shutdown`). Jamais d'exception ici : objet
        déjà fermé, double invisible en test, ou chaîne d'attributs absente
        selon la version de Python/urllib — dans tous ces cas, close()
        ci-dessus reste le seul comportement garanti."""
        try:
            self._response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass

    def lines(self):
        try:
            for raw_line in self._response:
                if self._closed:
                    return
                yield raw_line.decode("utf-8", errors="replace").rstrip("\n")
        except socket.timeout:
            if self._closed:
                return
            raise TransportTimeoutError("délai dépassé") from None
        except urllib.error.URLError:
            if self._closed:
                return
            raise TransportNetworkError("réseau indisponible") from None
        except Exception:
            # close() appelé depuis un AUTRE fil pendant une lecture
            # bloquante (ex. cancel() d'une recherche d'adversaire humain,
            # seek.py) interrompt la lecture en cours — la nature exacte de
            # l'exception levée par http.client/socket dépend du point
            # précis où la lecture a été coupée et de la version de Python :
            # ValueError observé historiquement, et AttributeError (attribut
            # interne devenu None après close()) observé en pratique sur un
            # essai réel (issue #328, 14/11/2026 — recherche d'adversaire
            # humain, flux d'évènements fermé pendant que ce générateur
            # attendait la ligne suivante). self._closed est déjà vrai à cet
            # instant (close() le positionne AVANT de fermer la réponse,
            # voir ci-dessous) : fin normale du générateur, jamais une erreur
            # réseau. Toute autre exception, non liée à une fermeture
            # volontaire, continue d'être remontée telle quelle à l'appelant
            # (jamais avalée en silence).
            if self._closed:
                return
            raise
        finally:
            self.close()
