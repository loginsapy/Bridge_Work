"""
Webhook service — envía notificaciones HTTP a sistemas externos (Slack, Teams, genérico).

Configuración almacenada en SystemSettings key='webhooks' como JSON:
[
  {
    "id": "uuid",
    "name": "Slack #proyectos",
    "url": "https://hooks.slack.com/...",
    "events": ["task.completed", "task.status_changed", "task.created"],
    "active": true,
    "secret": "opcional-para-hmac"
  }
]

Eventos disponibles:
  task.created          — nueva tarea creada
  task.status_changed   — cambio de estado de tarea
  task.completed        — tarea marcada como completada
  task.assigned         — tarea asignada a un usuario
"""

import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests as http_requests

logger = logging.getLogger(__name__)

# Eventos soportados
EVENTS = {
    'task.created': 'Tarea creada',
    'task.updated': 'Tarea editada',
    'task.status_changed': 'Cambio de estado de tarea',
    'task.completed': 'Tarea completada',
    'task.assigned': 'Tarea asignada',
}


def _load_webhooks() -> List[Dict]:
    """Carga la lista de webhooks desde SystemSettings."""
    try:
        from app.models import SystemSettings
        raw = SystemSettings.get('webhooks', '[]')
        if isinstance(raw, list):
            return raw
        return json.loads(raw) if raw else []
    except Exception as e:
        logger.error('Error loading webhooks: %s', e)
        return []


def _save_webhooks(webhooks: List[Dict]) -> None:
    """Guarda la lista de webhooks en SystemSettings."""
    from app.models import SystemSettings
    from app import db
    SystemSettings.set('webhooks', webhooks, category='notifications', value_type='json')
    db.session.commit()


def get_webhooks() -> List[Dict]:
    """Devuelve todos los webhooks configurados."""
    return _load_webhooks()


def upsert_webhook(webhook_id: Optional[str], name: str, url: str,
                   events: List[str], secret: str = '', active: bool = True) -> Dict:
    """Crea o actualiza un webhook. Retorna el webhook guardado."""
    webhooks = _load_webhooks()
    now = datetime.now().isoformat()

    if webhook_id:
        for i, wh in enumerate(webhooks):
            if wh.get('id') == webhook_id:
                webhooks[i] = {**wh, 'name': name, 'url': url, 'events': events,
                               'secret': secret, 'active': active, 'updated_at': now}
                _save_webhooks(webhooks)
                return webhooks[i]

    # Nuevo webhook
    new_wh = {
        'id': str(uuid.uuid4()),
        'name': name,
        'url': url,
        'events': events,
        'secret': secret,
        'active': active,
        'created_at': now,
        'updated_at': now,
    }
    webhooks.append(new_wh)
    _save_webhooks(webhooks)
    return new_wh


def delete_webhook(webhook_id: str) -> bool:
    """Elimina un webhook. Retorna True si fue encontrado y borrado."""
    webhooks = _load_webhooks()
    before = len(webhooks)
    webhooks = [wh for wh in webhooks if wh.get('id') != webhook_id]
    if len(webhooks) < before:
        _save_webhooks(webhooks)
        return True
    return False


def _build_signature(body: bytes, secret: str) -> str:
    """Genera firma HMAC-SHA256 para el payload."""
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _is_slack_url(url: str) -> bool:
    return 'hooks.slack.com' in url


def _is_teams_url(url: str) -> bool:
    return 'webhook.office.com' in url or 'outlook.office.com' in url


def _build_slack_payload(event: str, data: Dict) -> Dict:
    """Formatea el payload en formato Slack Block Kit."""
    color_map = {
        'task.completed': '#198754',
        'task.created': '#0073ea',
        'task.status_changed': '#fd7e14',
        'task.assigned': '#a25ddc',
    }
    status_labels = {
        'BACKLOG': 'Backlog', 'IN_PROGRESS': 'En Progreso',
        'IN_REVIEW': 'En Revisión', 'COMPLETED': 'Completado',
    }
    color = color_map.get(event, '#6c757d')
    title = EVENTS.get(event, event)

    fields = []
    if data.get('project_name'):
        fields.append({'title': 'Proyecto', 'value': data['project_name'], 'short': True})
    if data.get('user_name'):
        fields.append({'title': 'Usuario', 'value': data['user_name'], 'short': True})
    if data.get('new_status'):
        label = status_labels.get(data['new_status'], data['new_status'])
        if data.get('old_status'):
            old_label = status_labels.get(data['old_status'], data['old_status'])
            fields.append({'title': 'Estado', 'value': f'{old_label} → {label}', 'short': True})
        else:
            fields.append({'title': 'Estado', 'value': label, 'short': True})

    return {
        'attachments': [{
            'color': color,
            'title': f'{title}: {data.get("task_title", "")}',
            'fields': fields,
            'footer': 'BridgeWork',
            'ts': int(datetime.now().timestamp()),
        }]
    }


def _build_teams_payload(event: str, data: Dict) -> Dict:
    """Formatea el payload en formato Microsoft Teams Adaptive Card."""
    title = EVENTS.get(event, event)
    facts = []
    if data.get('project_name'):
        facts.append({'name': 'Proyecto', 'value': data['project_name']})
    if data.get('user_name'):
        facts.append({'name': 'Usuario', 'value': data['user_name']})
    if data.get('new_status'):
        facts.append({'name': 'Estado', 'value': data['new_status']})

    return {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'themeColor': '0073ea',
        'summary': f'{title}: {data.get("task_title", "")}',
        'sections': [{
            'activityTitle': f'**{title}**',
            'activitySubtitle': data.get('task_title', ''),
            'facts': facts,
        }]
    }


def _build_generic_payload(event: str, data: Dict) -> Dict:
    """Payload genérico JSON estándar."""
    return {
        'event': event,
        'timestamp': datetime.now().isoformat(),
        'data': data,
    }


def _save_delivery(webhook: Dict, event: str, success: bool,
                   status_code: Optional[int], error: Optional[str],
                   duration_ms: int, is_test: bool = False) -> None:
    """Persiste el resultado de un intento de entrega en la BD."""
    try:
        from app import db
        from app.models import WebhookDelivery
        record = WebhookDelivery(
            webhook_id=webhook.get('id', ''),
            webhook_name=webhook.get('name', ''),
            event=event,
            url=webhook.get('url', ''),
            success=success,
            status_code=status_code,
            error_message=error,
            duration_ms=duration_ms,
            is_test=is_test,
            created_at=datetime.now(),
        )
        db.session.add(record)
        db.session.commit()
    except Exception as exc:
        logger.error('Error saving webhook delivery record: %s', exc)


def _send_one(webhook: Dict, event: str, data: Dict, is_test: bool = False,
              max_retries: int = 2) -> None:
    """Envía el payload a un webhook específico (ejecutado en hilo separado).
    Reintenta hasta max_retries veces ante errores de red (no ante 4xx/5xx del receptor).
    """
    url = webhook.get('url', '')
    secret = webhook.get('secret', '')

    if _is_slack_url(url):
        payload = _build_slack_payload(event, data)
    elif _is_teams_url(url):
        payload = _build_teams_payload(event, data)
    else:
        payload = _build_generic_payload(event, data)
        if is_test:
            payload['_test'] = True

    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json', 'User-Agent': 'BridgeWork-Webhooks/1.0'}
    if secret:
        headers['X-BridgeWork-Signature'] = _build_signature(body, secret)

    last_error: Optional[str] = None
    last_status: Optional[int] = None
    attempt = 0

    while attempt <= max_retries:
        t0 = time.monotonic()
        try:
            resp = http_requests.post(url, data=body, headers=headers, timeout=10)
            duration_ms = int((time.monotonic() - t0) * 1000)
            last_status = resp.status_code

            if resp.status_code < 400:
                logger.debug('Webhook %s dispatched event %s → HTTP %s (%dms)',
                             webhook.get('name'), event, resp.status_code, duration_ms)
                _save_delivery(webhook, event, True, resp.status_code, None, duration_ms, is_test)
                return

            # 4xx/5xx — receptor rechazó, no reintentar
            last_error = resp.text[:300]
            logger.warning('Webhook %s (%s) returned HTTP %s: %s',
                           webhook.get('name'), url, resp.status_code, last_error)
            _save_delivery(webhook, event, False, resp.status_code, last_error, duration_ms, is_test)
            return

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            last_error = str(exc)
            logger.warning('Webhook %s attempt %d/%d failed: %s',
                           webhook.get('name'), attempt + 1, max_retries + 1, exc)
            if attempt < max_retries:
                time.sleep(2 ** attempt)   # backoff: 1s, 2s
            attempt += 1

    # Todos los intentos fallaron
    logger.error('Webhook %s (%s) failed after %d attempts for event %s: %s',
                 webhook.get('name'), url, max_retries + 1, event, last_error)
    _save_delivery(webhook, event, False, last_status, last_error,
                   int((time.monotonic()) * 1000), is_test)


def dispatch(event: str, data: Dict) -> None:
    """
    Envía el evento a todos los webhooks activos que escuchen ese evento.
    Se ejecuta en hilos background para no bloquear el request.
    """
    if event not in EVENTS:
        logger.warning('Unknown webhook event: %s', event)
        return

    webhooks = _load_webhooks()
    active = [wh for wh in webhooks if wh.get('active') and event in wh.get('events', [])]

    for webhook in active:
        t = threading.Thread(target=_send_one, args=(webhook, event, data), daemon=True)
        t.start()


def test_webhook(webhook_id: str) -> Dict:
    """Envía un payload de prueba a un webhook. Retorna resultado síncrono."""
    webhooks = _load_webhooks()
    wh = next((w for w in webhooks if w.get('id') == webhook_id), None)
    if not wh:
        return {'success': False, 'error': 'Webhook no encontrado'}

    url = wh.get('url', '')
    secret = wh.get('secret', '')
    data = {
        'task_id': 0,
        'task_title': 'Tarea de prueba',
        'project_id': 0,
        'project_name': 'Proyecto de prueba',
        'new_status': 'COMPLETED',
        'user_name': 'BridgeWork',
    }

    try:
        if _is_slack_url(url):
            payload = _build_slack_payload('task.completed', data)
        elif _is_teams_url(url):
            payload = _build_teams_payload('task.completed', data)
        else:
            payload = _build_generic_payload('task.completed', data)
            payload['_test'] = True

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'User-Agent': 'BridgeWork-Webhooks/1.0'}
        if secret:
            headers['X-BridgeWork-Signature'] = _build_signature(body, secret)

        t0 = time.monotonic()
        resp = http_requests.post(url, data=body, headers=headers, timeout=10)
        duration_ms = int((time.monotonic() - t0) * 1000)
        success = resp.status_code < 400
        _save_delivery(wh, 'task.completed', success, resp.status_code,
                       None if success else resp.text[:300], duration_ms, is_test=True)
        return {
            'success': success,
            'status_code': resp.status_code,
            'response': resp.text[:300],
            'duration_ms': duration_ms,
        }
    except Exception as e:
        _save_delivery(wh, 'task.completed', False, None, str(e), 0, is_test=True)
        return {'success': False, 'error': str(e)}
