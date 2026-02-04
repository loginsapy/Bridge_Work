"""
License service for BridgeWork - comunicación con servidor de licencias.
Basado en implementación de referencia de LoginTickets.
"""

import hashlib
import logging
import platform
import socket
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from app import db
from app.models import License, SystemSettings

logger = logging.getLogger(__name__)


class LicenseError(Exception):
    """Excepción para errores de licencia."""
    pass


class LicenseService:
    """Servicio de gestión de licencias."""
    
    API_BASE_URL = "https://licencias.login.com.py/api/v1/license"
    PRODUCT_CODE = "BRIDGEWORK"
    TIMEOUT = 30
    
    _cache: Dict[str, Any] = {}
    _cache_time: Optional[datetime] = None
    CACHE_TTL = 300  # 5 minutos
    
    @classmethod
    def _get_hardware_id(cls) -> str:
        """Obtiene o genera el hardware_id único para esta instalación."""
        setting = SystemSettings.query.filter_by(key='hardware_id').first()
        if setting and setting.value:
            return setting.value
        
        # Generar nuevo hardware_id
        try:
            mac = uuid.getnode()
            hostname = socket.gethostname()
            unique_str = f"{mac}-{hostname}-bridgework"
            hardware_id = hashlib.md5(unique_str.encode()).hexdigest()
        except Exception:
            hardware_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
        
        # Guardar en SystemSettings
        if setting:
            setting.value = hardware_id
        else:
            setting = SystemSettings(key='hardware_id', value=hardware_id)
            db.session.add(setting)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        return hardware_id
    
    @classmethod
    def _get_device_info(cls) -> Dict[str, str]:
        """Obtiene información del dispositivo."""
        return {
            "nombre": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}"
        }
    
    @classmethod
    def _make_request(cls, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Realiza una petición al servidor de licencias.
        
        Returns:
            Dict con keys: success, status_code, data, message
        """
        url = f"{cls.API_BASE_URL}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        logger.info(f"Request to {url}")
        logger.debug(f"Payload: {payload}")
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=cls.TIMEOUT
            )
            
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response body: {response.text}")
            
            # Intentar parsear JSON
            try:
                data = response.json()
            except Exception:
                data = {"message": response.text}
            
            return {
                "success": response.status_code in (200, 201),
                "status_code": response.status_code,
                "data": data,
                "message": data.get("message", "")
            }
            
        except requests.Timeout:
            logger.error("Request timeout")
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "message": "Tiempo de espera agotado al conectar con el servidor"
            }
        except requests.ConnectionError:
            logger.error("Connection error")
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "message": "No se pudo conectar con el servidor de licencias"
            }
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "message": str(e)
            }
    
    @classmethod
    def activate(cls, license_key: str) -> Dict[str, Any]:
        """
        Activa una licencia. Si ya está activa, valida y guarda.
        
        Args:
            license_key: Clave de licencia a activar
            
        Returns:
            Dict con información del resultado
        """
        hardware_id = cls._get_hardware_id()
        device_info = cls._get_device_info()
        
        # Primero intentar validar (por si ya está activa)
        validate_payload = {
            "license_key": license_key,
            "product_code": cls.PRODUCT_CODE,
            "hardware_id": hardware_id
        }
        
        validate_result = cls._make_request("validate", validate_payload)
        
        if validate_result["success"]:
            response_data = validate_result["data"]
            data = response_data.get("data", response_data)
            
            if data.get("valid"):
                license_data = data.get("license", {})
                
                # Guardar en base de datos
                cls._save_license(
                    license_key=license_key,
                    hardware_id=hardware_id,
                    license_data=license_data,
                    is_active=True
                )
                
                # Limpiar cache
                cls._cache = {}
                cls._cache_time = None
                
                return {
                    "success": True,
                    "message": "Licencia activada correctamente",
                    "license": license_data
                }
        
        # Si validate falla, intentar activate
        payload = {
            "license_key": license_key,
            "hardware_id": hardware_id,
            "device_info": device_info
        }
        
        result = cls._make_request("activate", payload)
        
        if result["success"]:
            response_data = result["data"]
            license_data = response_data.get("data", {}).get("license", {})
            
            if not license_data:
                license_data = response_data.get("data", response_data)
            
            cls._save_license(
                license_key=license_key,
                hardware_id=hardware_id,
                license_data=license_data,
                is_active=True
            )
            
            cls._cache = {}
            cls._cache_time = None
            
            return {
                "success": True,
                "message": "Licencia activada correctamente",
                "license": license_data
            }
        else:
            status_code = result["status_code"]
            message = result["message"]
            
            if status_code == 404:
                message = "Licencia no encontrada. Verifique la clave."
            elif status_code == 409:
                message = "La licencia ya está activada en otro dispositivo."
            
            return {
                "success": False,
                "message": message,
                "status_code": status_code
            }
    
    @classmethod
    def validate(cls, license_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Valida una licencia.
        
        Args:
            license_key: Clave de licencia (opcional, usa la guardada si no se proporciona)
            
        Returns:
            Dict con información de validación
        """
        # Verificar cache
        if cls._cache and cls._cache_time:
            elapsed = (datetime.utcnow() - cls._cache_time).total_seconds()
            if elapsed < cls.CACHE_TTL:
                return cls._cache
        
        # Obtener licencia de la base de datos si no se proporciona
        if not license_key:
            license_record = License.get_active()
            if not license_record:
                return {
                    "success": False,
                    "valid": False,
                    "message": "No hay licencia activa"
                }
            license_key = license_record.license_key
        
        hardware_id = cls._get_hardware_id()
        
        payload = {
            "license_key": license_key,
            "product_code": cls.PRODUCT_CODE,
            "hardware_id": hardware_id
        }
        
        result = cls._make_request("validate", payload)
        
        if result["success"]:
            response_data = result["data"]
            
            # La respuesta tiene estructura: {success: true, data: {valid: true, license: {...}}}
            data = response_data.get("data", response_data)
            is_valid = data.get("valid", False)
            license_info = data.get("license", {})
            
            validation_result = {
                "success": True,
                "valid": is_valid,
                "license": license_info,
                "message": "Licencia válida" if is_valid else "Licencia inválida"
            }
            
            # Actualizar cache
            cls._cache = validation_result
            cls._cache_time = datetime.utcnow()
            
            # Actualizar registro en BD
            if is_valid:
                cls._update_license_status(license_key, license_info)
            
            return validation_result
        else:
            return {
                "success": False,
                "valid": False,
                "message": result["message"]
            }
    
    @classmethod
    def deactivate(cls, license_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Desactiva una licencia.
        
        Args:
            license_key: Clave de licencia (opcional)
            
        Returns:
            Dict con resultado de desactivación
        """
        if not license_key:
            license_record = License.get_active()
            if not license_record:
                return {
                    "success": False,
                    "message": "No hay licencia activa para desactivar"
                }
            license_key = license_record.license_key
        
        hardware_id = cls._get_hardware_id()
        
        payload = {
            "license_key": license_key,
            "hardware_id": hardware_id
        }
        
        result = cls._make_request("deactivate", payload)
        
        if result["success"]:
            # Desactivar en base de datos
            license_record = License.query.filter_by(
                license_key=license_key,
                status='ACTIVE'
            ).first()
            
            if license_record:
                license_record.status = 'INACTIVE'
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            
            # Limpiar cache
            cls._cache = {}
            cls._cache_time = None
            
            return {
                "success": True,
                "message": "Licencia desactivada correctamente"
            }
        else:
            return {
                "success": False,
                "message": result["message"]
            }
    
    @classmethod
    def _save_license(
        cls,
        license_key: str,
        hardware_id: str,
        license_data: Dict[str, Any],
        is_active: bool = True
    ) -> None:
        """Guarda o actualiza la licencia en la base de datos."""
        try:
            # Desactivar licencias anteriores
            License.query.filter_by(status='ACTIVE').update({"status": 'INACTIVE'})
            
            # Buscar o crear registro
            license_record = License.query.filter_by(license_key=license_key).first()
            
            new_status = 'ACTIVE' if is_active else 'INACTIVE'
            
            if license_record:
                license_record.hardware_id = hardware_id
                license_record.status = new_status
                license_record.expires_at = cls._parse_date(license_data.get("expires_at"))
                license_record.activated_at = datetime.utcnow()
                license_record.last_validated_at = datetime.utcnow()
                license_record.license_type = license_data.get("type")
                license_record.product_code = license_data.get("product_code", cls.PRODUCT_CODE)
            else:
                license_record = License(
                    license_key=license_key,
                    hardware_id=hardware_id,
                    status=new_status,
                    product_code=license_data.get("product_code", cls.PRODUCT_CODE),
                    expires_at=cls._parse_date(license_data.get("expires_at")),
                    activated_at=datetime.utcnow(),
                    last_validated_at=datetime.utcnow(),
                    license_type=license_data.get("type")
                )
                db.session.add(license_record)
            
            db.session.commit()
            logger.info(f"License saved: {license_key}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving license: {e}")
    
    @classmethod
    def _update_license_status(cls, license_key: str, license_info: Dict[str, Any]) -> None:
        """Actualiza el estado de la licencia después de validación."""
        try:
            license_record = License.query.filter_by(license_key=license_key).first()
            if license_record:
                license_record.last_validated_at = datetime.utcnow()
                if license_info.get("expires_at"):
                    license_record.expires_at = cls._parse_date(license_info["expires_at"])
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating license status: {e}")
    
    @classmethod
    def _parse_date(cls, date_str: Optional[str]) -> Optional[datetime]:
        """Parsea una fecha desde string."""
        if not date_str:
            return None
        try:
            # Intentar varios formatos
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(date_str[:19], fmt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None
    
    @classmethod
    def get_current_license(cls) -> Optional[Dict[str, Any]]:
        """Obtiene información de la licencia activa actual."""
        license_record = License.get_active()
        if not license_record:
            return None
        
        return {
            "license_key": license_record.license_key,
            "hardware_id": license_record.hardware_id,
            "status": license_record.status,
            "expires_at": license_record.expires_at.isoformat() if license_record.expires_at else None,
            "activated_at": license_record.activated_at.isoformat() if license_record.activated_at else None,
            "last_validated_at": license_record.last_validated_at.isoformat() if license_record.last_validated_at else None
        }
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """
        Obtiene el estado completo de la licencia.
        
        Returns:
            Dict con estado de licencia
        """
        license_record = License.get_active()
        
        if not license_record:
            return {
                "has_license": False,
                "is_valid": False,
                "license": None,
                "message": "No hay licencia activa"
            }
        
        # Devolver el objeto license para el template
        return {
            "has_license": True,
            "is_valid": license_record.is_valid(),
            "license": license_record,
            "license_key": license_record.license_key,
            "status": license_record.status,
            "expires_at": license_record.expires_at.isoformat() if license_record.expires_at else None,
            "last_validated_at": license_record.last_validated_at.isoformat() if license_record.last_validated_at else None,
            "message": "Licencia activa" if license_record.is_valid() else "Licencia inválida"
        }


# Funciones de compatibilidad con código existente
def activate_license(license_key: str) -> Dict[str, Any]:
    """Wrapper de compatibilidad."""
    return LicenseService.activate(license_key)


def validate_license(license_key: Optional[str] = None) -> Dict[str, Any]:
    """Wrapper de compatibilidad."""
    return LicenseService.validate(license_key)


def deactivate_license(license_key: Optional[str] = None) -> Dict[str, Any]:
    """Wrapper de compatibilidad."""
    return LicenseService.deactivate(license_key)


def get_license_status() -> Dict[str, Any]:
    """Wrapper de compatibilidad."""
    return LicenseService.get_status()


def check_license_status() -> Dict[str, Any]:
    """Wrapper de compatibilidad."""
    return LicenseService.get_status()


def get_hardware_id() -> str:
    """Wrapper de compatibilidad."""
    return LicenseService._get_hardware_id()
