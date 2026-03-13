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


def _send_one(webhook: Dict, event: str, data: Dict) -> None:
    """Envía el payload a un webhook específico (ejecutado en hilo separado)."""
    url = webhook.get('url', '')
    secret = webhook.get('secret', '')

    try:
        if _is_slack_url(url):
            payload = _build_slack_payload(event, data)
        elif _is_teams_url(url):
            payload = _build_teams_payload(event, data)
        else:
            payload = _build_generic_payload(event, data)

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'User-Agent': 'BridgeWork-Webhooks/1.0'}
        if secret:
            headers['X-BridgeWork-Signature'] = _build_signature(body, secret)

        resp = http_requests.post(url, data=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning('Webhook %s (%s) returned HTTP %s: %s',
                           webhook.get('name'), url, resp.status_code, resp.text[:200])
        else:
            logger.debug('Webhook %s dispatched event %s → %s',
                         webhook.get('name'), event, resp.status_code)
    except Exception as e:
        logger.error('Webhook %s (%s) failed for event %s: %s',
                     webhook.get('name'), url, event, e)


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

        resp = http_requests.post(url, data=body, headers=headers, timeout=10)
        return {
            'success': resp.status_code < 400,
            'status_code': resp.status_code,
            'response': resp.text[:300],
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}
