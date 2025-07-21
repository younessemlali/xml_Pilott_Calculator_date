"""
Constantes pour l'application Pilott Date Editor
"""

# Encodage des fichiers XML
XML_ENCODING = 'ISO-8859-1'

# Namespaces HR-XML
NAMESPACES = {
    'hr': 'http://www.hr-xml.org/3',
    'oa': 'http://www.openapplications.org/oagis/9',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

# Formats de date et heure
DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TIMEZONE = 'Europe/Paris'

# Patterns de noms de fichiers
INPUT_FILE_PATTERN = r'ASS_\d+_A_ETT\.xml'
OUTPUT_FILE_PATTERN = 'ASS_{timestamp}_AU_ETT.xml'
STAFFING_ACTION_PATTERN = 'ASS_{timestamp}_SA_ETT.xml'

# Chemins vers les ressources
XSD_PATH = 'resources/xsd/'

# Règles métier
MAX_FLEXIBILITY_DAYS = 10
FLEXIBILITY_DIVISOR = 5

# Codes pour StaffingAction
ACTION_REASON_CODE_FLEXIBILITY = 'PilOTT:FlexibilityUseDate'
ACTION_TYPE_DELETE = 'delete'

# Statuts de mise à jour
PROCESS_STATUS_UPDATE = 'update'
ASSIGNMENT_STATUS_ACTIVE = 'active'

# Messages d'erreur
ERROR_MESSAGES = {
    'invalid_actual_end': "La date de fin réelle doit être <= à la date de flexibilité maximale",
    'invalid_file_format': "Format de fichier invalide. Attendu: ASS_*_A_ETT.xml",
    'parsing_error': "Erreur lors de l'analyse du fichier XML",
    'validation_error': "Le fichier XML ne respecte pas le schéma XSD",
    'encoding_error': "Erreur d'encodage. Le fichier doit être en ISO-8859-1",
    'multiple_flexibility_dates': "Plusieurs dates de souplesse actives détectées",
    'assignment_id_mismatch': "L'identifiant du contrat ne correspond pas"
}
