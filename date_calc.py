"""
Module de calcul et validation des dates selon les règles Pilott
"""

from datetime import date, datetime, timedelta
from typing import Tuple, Optional
import pytz
from dateutil import parser

from .constants import (
    DATE_FORMAT, 
    DATETIME_FORMAT, 
    TIMEZONE,
    MAX_FLEXIBILITY_DAYS,
    FLEXIBILITY_DIVISOR,
    ERROR_MESSAGES
)


def calc_flex_range(start: date, expected_end: date) -> Tuple[date, date, int]:
    """
    Calcule les dates de flexibilité min et max selon la règle Pilott.
    
    Args:
        start: Date de début de mission
        expected_end: Date de fin prévue
        
    Returns:
        Tuple (flex_min, flex_max, nombre_jours)
    """
    # Durée calendaire (inclut le premier et dernier jour)
    duration = (expected_end - start).days + 1
    
    # Nombre de jours de flexibilité = ⌊(durée / 5)⌋, plafonné à 10
    flex_days = min(MAX_FLEXIBILITY_DAYS, max(1, duration // FLEXIBILITY_DIVISOR))
    
    flex_min = expected_end - timedelta(days=flex_days)
    flex_max = expected_end + timedelta(days=flex_days)
    
    return flex_min, flex_max, flex_days


def validate_actual_end_date(actual_end: date, flex_max: date) -> bool:
    """
    Vérifie que la date de fin réelle respecte la contrainte de flexibilité.
    
    Args:
        actual_end: Date de fin réelle
        flex_max: Date de flexibilité maximale
        
    Returns:
        True si valide, False sinon
    """
    return actual_end <= flex_max


def parse_date(date_str: str) -> date:
    """
    Parse une date au format YYYY-MM-DD.
    
    Args:
        date_str: Chaîne de date
        
    Returns:
        Objet date
    """
    return datetime.strptime(date_str, DATE_FORMAT).date()


def format_date(date_obj: date) -> str:
    """
    Formate une date au format YYYY-MM-DD.
    
    Args:
        date_obj: Objet date
        
    Returns:
        Chaîne formatée
    """
    return date_obj.strftime(DATE_FORMAT)


def parse_datetime_utc(datetime_str: str) -> datetime:
    """
    Parse un horodatage UTC au format ISO.
    
    Args:
        datetime_str: Chaîne datetime UTC
        
    Returns:
        Objet datetime aware UTC
    """
    # Gère plusieurs formats possibles
    try:
        # Format avec Z
        if datetime_str.endswith('Z'):
            dt = datetime.strptime(datetime_str, DATETIME_FORMAT)
            return pytz.UTC.localize(dt)
        # Format avec +00:00
        else:
            return parser.parse(datetime_str)
    except Exception:
        # Fallback sur dateutil parser
        return parser.parse(datetime_str)


def format_datetime_utc(dt: datetime) -> str:
    """
    Formate un datetime en UTC au format ISO avec Z.
    
    Args:
        dt: Objet datetime
        
    Returns:
        Chaîne formatée
    """
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        dt = dt.astimezone(pytz.UTC)
    
    return dt.strftime(DATETIME_FORMAT)


def utc_to_paris(dt: datetime) -> datetime:
    """
    Convertit un datetime UTC vers Europe/Paris.
    
    Args:
        dt: Datetime UTC
        
    Returns:
        Datetime Europe/Paris
    """
    paris_tz = pytz.timezone(TIMEZONE)
    return dt.astimezone(paris_tz)


def paris_to_utc(dt: datetime) -> datetime:
    """
    Convertit un datetime Europe/Paris vers UTC.
    
    Args:
        dt: Datetime Europe/Paris
        
    Returns:
        Datetime UTC
    """
    if dt.tzinfo is None:
        paris_tz = pytz.timezone(TIMEZONE)
        dt = paris_tz.localize(dt)
    
    return dt.astimezone(pytz.UTC)


def validate_date_coherence(
    start_date: date,
    expected_end_date: date,
    actual_end_date: Optional[date] = None,
    flexibility_use_date: Optional[date] = None
) -> Tuple[bool, Optional[str]]:
    """
    Valide la cohérence globale des dates d'un contrat.
    
    Args:
        start_date: Date de début
        expected_end_date: Date de fin prévue
        actual_end_date: Date de fin réelle (optionnelle)
        flexibility_use_date: Date d'utilisation de la souplesse (optionnelle)
        
    Returns:
        Tuple (valide, message_erreur)
    """
    # Vérifier que la date de début est avant la fin prévue
    if start_date > expected_end_date:
        return False, "La date de début doit être antérieure à la date de fin prévue"
    
    # Calculer les dates de flexibilité
    flex_min, flex_max, _ = calc_flex_range(start_date, expected_end_date)
    
    # Si date de fin réelle fournie, vérifier qu'elle est dans les limites
    if actual_end_date:
        if not validate_actual_end_date(actual_end_date, flex_max):
            return False, ERROR_MESSAGES['invalid_actual_end']
        
        # La date de fin réelle ne peut pas être avant le début
        if actual_end_date < start_date:
            return False, "La date de fin réelle ne peut pas être antérieure au début de mission"
    
    # Si date de souplesse fournie, vérifier qu'elle est dans la plage
    if flexibility_use_date:
        if flexibility_use_date < flex_min or flexibility_use_date > flex_max:
            return False, f"La date de souplesse doit être entre {flex_min} et {flex_max}"
    
    return True, None


def calculate_duration(start_date: date, end_date: date) -> int:
    """
    Calcule la durée calendaire entre deux dates (inclusive).
    
    Args:
        start_date: Date de début
        end_date: Date de fin
        
    Returns:
        Nombre de jours
    """
    return (end_date - start_date).days + 1
