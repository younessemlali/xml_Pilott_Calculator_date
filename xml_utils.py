"""
Module de gestion XML pour les fichiers HR-XML Pilott
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import uuid
from pathlib import Path
import xmlschema

from .constants import (
    XML_ENCODING,
    NAMESPACES,
    DATE_FORMAT,
    OUTPUT_FILE_PATTERN,
    STAFFING_ACTION_PATTERN,
    PROCESS_STATUS_UPDATE,
    ASSIGNMENT_STATUS_ACTIVE,
    ACTION_REASON_CODE_FLEXIBILITY,
    XSD_PATH,
    ERROR_MESSAGES
)
from .date_calc import (
    parse_date,
    format_date,
    format_datetime_utc,
    calc_flex_range
)


# Enregistrer les namespaces pour ET
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


class ContractData:
    """Structure pour stocker les données d'un contrat"""
    def __init__(self):
        self.assignment_id = ""
        self.staffing_supplier_id = ""
        self.start_date = None
        self.expected_end_date = None
        self.actual_end_date = None
        self.flex_min_date = None
        self.flex_max_date = None
        self.flexibility_use_date = None
        self.original_tree = None
        self.filename = ""


def parse_contract_xml(xml_content: bytes, filename: str = "") -> ContractData:
    """
    Parse un fichier XML de contrat et extrait les données pertinentes.
    
    Args:
        xml_content: Contenu XML en bytes
        filename: Nom du fichier source
        
    Returns:
        ContractData avec les informations extraites
    """
    try:
        # Parser avec gestion de l'encodage ISO-8859-1
        root = ET.fromstring(xml_content.decode(XML_ENCODING))
        
        contract = ContractData()
        contract.filename = filename
        contract.original_tree = ET.ElementTree(root)
        
        # Extraire les identifiants
        assignment_elem = root.find('.//hr:Assignment', NAMESPACES)
        if assignment_elem is not None:
            # AssignmentId
            assignment_id_elem = assignment_elem.find('.//hr:AssignmentId', NAMESPACES)
            if assignment_id_elem is not None:
                contract.assignment_id = assignment_id_elem.text or ""
            
            # StaffingSupplierId
            supplier_elem = assignment_elem.find('.//hr:StaffingSupplierId', NAMESPACES)
            if supplier_elem is not None:
                contract.staffing_supplier_id = supplier_elem.text or ""
        
        # Extraire les dates
        date_range_elem = root.find('.//hr:AssignmentDateRange', NAMESPACES)
        if date_range_elem is not None:
            # StartDate
            start_elem = date_range_elem.find('hr:StartDate', NAMESPACES)
            if start_elem is not None and start_elem.text:
                contract.start_date = parse_date(start_elem.text)
            
            # ExpectedEndDate
            expected_end_elem = date_range_elem.find('hr:ExpectedEndDate', NAMESPACES)
            if expected_end_elem is not None and expected_end_elem.text:
                contract.expected_end_date = parse_date(expected_end_elem.text)
            
            # ActualEndDate (optionnel)
            actual_end_elem = date_range_elem.find('hr:ActualEndDate', NAMESPACES)
            if actual_end_elem is not None and actual_end_elem.text:
                contract.actual_end_date = parse_date(actual_end_elem.text)
            
            # FlexibilityMinDate
            flex_min_elem = date_range_elem.find('hr:FlexibilityMinDate', NAMESPACES)
            if flex_min_elem is not None and flex_min_elem.text:
                contract.flex_min_date = parse_date(flex_min_elem.text)
            
            # FlexibilityMaxDate
            flex_max_elem = date_range_elem.find('hr:FlexibilityMaxDate', NAMESPACES)
            if flex_max_elem is not None and flex_max_elem.text:
                contract.flex_max_date = parse_date(flex_max_elem.text)
        
        # Si les dates de flexibilité ne sont pas présentes, les calculer
        if contract.start_date and contract.expected_end_date:
            if not contract.flex_min_date or not contract.flex_max_date:
                flex_min, flex_max, _ = calc_flex_range(
                    contract.start_date, 
                    contract.expected_end_date
                )
                contract.flex_min_date = flex_min
                contract.flex_max_date = flex_max
        
        return contract
        
    except Exception as e:
        raise ValueError(f"{ERROR_MESSAGES['parsing_error']}: {str(e)}")


def update_contract_dates(contract: ContractData) -> None:
    """
    Met à jour les dates dans l'arbre XML du contrat.
    
    Args:
        contract: ContractData avec les nouvelles dates
    """
    if not contract.original_tree:
        return
    
    root = contract.original_tree.getroot()
    
    # Trouver ou créer AssignmentDateRange
    date_range_elem = root.find('.//hr:AssignmentDateRange', NAMESPACES)
    
    if date_range_elem is not None:
        # Mettre à jour les dates existantes
        _update_or_create_date_elem(date_range_elem, 'hr:StartDate', 
                                   format_date(contract.start_date))
        _update_or_create_date_elem(date_range_elem, 'hr:ExpectedEndDate', 
                                   format_date(contract.expected_end_date))
        
        if contract.actual_end_date:
            _update_or_create_date_elem(date_range_elem, 'hr:ActualEndDate', 
                                       format_date(contract.actual_end_date))
        
        _update_or_create_date_elem(date_range_elem, 'hr:FlexibilityMinDate', 
                                   format_date(contract.flex_min_date))
        _update_or_create_date_elem(date_range_elem, 'hr:FlexibilityMaxDate', 
                                   format_date(contract.flex_max_date))


def _update_or_create_date_elem(parent: ET.Element, tag: str, value: str) -> None:
    """Helper pour mettre à jour ou créer un élément date"""
    elem = parent.find(tag, NAMESPACES)
    if elem is None:
        elem = ET.SubElement(parent, tag)
    elem.text = value


def build_au_packet(contract: ContractData) -> ET.ElementTree:
    """
    Construit un paquet AU (AssignmentUpdate) à partir des données du contrat.
    
    Args:
        contract: ContractData avec les informations mises à jour
        
    Returns:
        ElementTree du paquet AU
    """
    # Créer la racine avec namespaces
    root = ET.Element('{' + NAMESPACES['hr'] + '}HRXMLRequest')
    for prefix, uri in NAMESPACES.items():
        root.set(f'xmlns:{prefix}', uri)
    
    # Header
    header = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Header')
    
    # TransactId
    transact_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TransactId')
    transact_elem.text = str(uuid.uuid4())
    
    # TimeStamp
    timestamp_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TimeStamp')
    timestamp_elem.text = format_datetime_utc(datetime.utcnow())
    
    # Body
    body = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Body')
    
    # Assignment avec attributs update
    assignment = ET.SubElement(body, '{' + NAMESPACES['hr'] + '}Assignment')
    assignment.set('processStatus', PROCESS_STATUS_UPDATE)
    assignment.set('assignmentStatus', ASSIGNMENT_STATUS_ACTIVE)
    
    # AssignmentId
    assignment_id_elem = ET.SubElement(assignment, '{' + NAMESPACES['hr'] + '}AssignmentId')
    assignment_id_elem.text = contract.assignment_id
    
    # StaffingSupplierId
    supplier_elem = ET.SubElement(assignment, '{' + NAMESPACES['hr'] + '}StaffingSupplierId')
    supplier_elem.text = contract.staffing_supplier_id
    
    # AssignmentDateRange
    date_range = ET.SubElement(assignment, '{' + NAMESPACES['hr'] + '}AssignmentDateRange')
    
    # Dates
    start_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}StartDate')
    start_elem.text = format_date(contract.start_date)
    
    expected_end_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}ExpectedEndDate')
    expected_end_elem.text = format_date(contract.expected_end_date)
    
    if contract.actual_end_date:
        actual_end_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}ActualEndDate')
        actual_end_elem.text = format_date(contract.actual_end_date)
    
    flex_min_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}FlexibilityMinDate')
    flex_min_elem.text = format_date(contract.flex_min_date)
    
    flex_max_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}FlexibilityMaxDate')
    flex_max_elem.text = format_date(contract.flex_max_date)
    
    return ET.ElementTree(root)


def build_staffing_action(contract: ContractData, 
                         flexibility_date: Optional[str] = None,
                         delete: bool = False) -> ET.ElementTree:
    """
    Construit un StaffingAction pour la date de souplesse.
    
    Args:
        contract: ContractData
        flexibility_date: Date de souplesse au format YYYY-MM-DD
        delete: Si True, génère une suppression de souplesse
        
    Returns:
        ElementTree du StaffingAction
    """
    # Structure similaire mais avec StaffingAction
    root = ET.Element('{' + NAMESPACES['hr'] + '}HRXMLRequest')
    for prefix, uri in NAMESPACES.items():
        root.set(f'xmlns:{prefix}', uri)
    
    # Header (similaire)
    header = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Header')
    transact_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TransactId')
    transact_elem.text = str(uuid.uuid4())
    timestamp_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TimeStamp')
    timestamp_elem.text = format_datetime_utc(datetime.utcnow())
    
    # Body avec StaffingAction
    body = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Body')
    staffing_action = ET.SubElement(body, '{' + NAMESPACES['hr'] + '}StaffingAction')
    
    # AssignmentId
    assignment_id_elem = ET.SubElement(staffing_action, '{' + NAMESPACES['hr'] + '}AssignmentId')
    assignment_id_elem.text = contract.assignment_id
    
    # ActionReasonCode
    reason_elem = ET.SubElement(staffing_action, '{' + NAMESPACES['hr'] + '}ActionReasonCode')
    reason_elem.text = ACTION_REASON_CODE_FLEXIBILITY
    
    # ActionTypeComments
    comments_elem = ET.SubElement(staffing_action, '{' + NAMESPACES['hr'] + '}ActionTypeComments')
    comments_elem.text = 'delete' if delete else flexibility_date
    
    return ET.ElementTree(root)


def write_xml(tree: ET.ElementTree, output_path: str) -> None:
    """
    Écrit un ElementTree dans un fichier XML avec encodage ISO-8859-1.
    
    Args:
        tree: ElementTree à écrire
        output_path: Chemin de sortie
    """
    # Indenter pour la lisibilité
    _indent(tree.getroot())
    
    # Écrire avec déclaration XML et encodage
    tree.write(output_path, 
               encoding=XML_ENCODING,
               xml_declaration=True,
               method='xml')


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Helper pour indenter le XML"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def validate_xml_schema(xml_path: str, xsd_name: str = 'hrxml_assignment.xsd') -> Tuple[bool, Optional[str]]:
    """
    Valide un fichier XML contre le schéma XSD.
    
    Args:
        xml_path: Chemin du fichier XML
        xsd_name: Nom du fichier XSD
        
    Returns:
        Tuple (valide, message_erreur)
    """
    try:
        xsd_path = Path(XSD_PATH) / xsd_name
        if not xsd_path.exists():
            return True, None  # Si pas de XSD, on considère valide
        
        schema = xmlschema.XMLSchema(str(xsd_path))
        schema.validate(xml_path)
        return True, None
        
    except xmlschema.XMLSchemaException as e:
        return False, f"{ERROR_MESSAGES['validation_error']}: {str(e)}"
    except Exception as e:
        return False, f"Erreur de validation: {str(e)}"


def generate_output_filename(file_type: str = 'AU') -> str:
    """
    Génère un nom de fichier de sortie avec timestamp.
    
    Args:
        file_type: 'AU' ou 'SA' (StaffingAction)
        
    Returns:
        Nom de fichier
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    if file_type == 'SA':
        return STAFFING_ACTION_PATTERN.format(timestamp=timestamp)
    else:
        return OUTPUT_FILE_PATTERN.format(timestamp=timestamp)
