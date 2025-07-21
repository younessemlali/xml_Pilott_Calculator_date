"""
Application Streamlit pour l'édition des dates de contrats HR-XML Pilott
"""

import streamlit as st
from datetime import datetime, date, timedelta
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re
import xml.etree.ElementTree as ET
import uuid
import pytz
from dateutil import parser
import io

# Configuration de la page
st.set_page_config(
    page_title="Pilott Date Editor",
    page_icon="📅",
    layout="wide"
)

# ============= CONSTANTS =============
XML_ENCODING = 'ISO-8859-1'

# Support des deux versions HR-XML
NAMESPACES_V3 = {
    'hr': 'http://www.hr-xml.org/3',
    'oa': 'http://www.openapplications.org/oagis/9',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

NAMESPACES_V2 = {
    'hr': 'http://ns.hr-xml.org/2004-08-02',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

# Namespace par défaut (sera détecté dynamiquement)
NAMESPACES = NAMESPACES_V2

DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TIMEZONE = 'Europe/Paris'

INPUT_FILE_PATTERN = r'ASS_\d+_A_ETT\.xml'
OUTPUT_FILE_PATTERN = 'ASS_{timestamp}_AU_ETT.xml'
STAFFING_ACTION_PATTERN = 'ASS_{timestamp}_SA_ETT.xml'

MAX_FLEXIBILITY_DAYS = 10
FLEXIBILITY_DIVISOR = 5

PROCESS_STATUS_UPDATE = 'update'
ASSIGNMENT_STATUS_ACTIVE = 'active'
ACTION_REASON_CODE_FLEXIBILITY = 'PilOTT:FlexibilityUseDate'

ERROR_MESSAGES = {
    'invalid_actual_end': "La date de fin réelle doit être <= à la date de flexibilité maximale",
    'invalid_file_format': "Format de fichier invalide. Attendu: ASS_*_A_ETT.xml",
    'parsing_error': "Erreur lors de l'analyse du fichier XML",
    'validation_error': "Le fichier XML ne respecte pas le schéma XSD",
    'encoding_error': "Erreur d'encodage. Le fichier doit être en ISO-8859-1",
}

# Enregistrer les namespaces
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

# ============= DATE CALCULATIONS =============

def calc_flex_range(start: date, expected_end: date) -> Tuple[date, date, int]:
    """Calcule les dates de flexibilité min et max selon la règle Pilott."""
    duration = (expected_end - start).days + 1
    flex_days = min(MAX_FLEXIBILITY_DAYS, max(1, duration // FLEXIBILITY_DIVISOR))
    flex_min = expected_end - timedelta(days=flex_days)
    flex_max = expected_end + timedelta(days=flex_days)
    return flex_min, flex_max, flex_days

def validate_date_coherence(start_date: date, expected_end_date: date, 
                          actual_end_date: Optional[date] = None) -> Tuple[bool, Optional[str]]:
    """Valide la cohérence globale des dates d'un contrat."""
    if start_date > expected_end_date:
        return False, "La date de début doit être antérieure à la date de fin prévue"
    
    if actual_end_date:
        flex_min, flex_max, _ = calc_flex_range(start_date, expected_end_date)
        if actual_end_date > flex_max:
            return False, ERROR_MESSAGES['invalid_actual_end']
        if actual_end_date < start_date:
            return False, "La date de fin réelle ne peut pas être antérieure au début de mission"
    
    return True, None

def parse_date(date_str: str) -> date:
    """Parse une date au format YYYY-MM-DD."""
    return datetime.strptime(date_str, DATE_FORMAT).date()

def format_date(date_obj: Optional[date]) -> str:
    """Formate une date au format YYYY-MM-DD."""
    if date_obj is None:
        return ""
    return date_obj.strftime(DATE_FORMAT)

def format_datetime_utc(dt: datetime) -> str:
    """Formate un datetime en UTC au format ISO avec Z."""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        dt = dt.astimezone(pytz.UTC)
    return dt.strftime(DATETIME_FORMAT)

# ============= XML HANDLING =============

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
        self.original_tree = None
        self.filename = ""

def parse_contract_xml(xml_content: bytes, filename: str = "") -> List[ContractData]:
    """Parse un fichier XML et extrait TOUS les contrats (peut y en avoir plusieurs)."""
    contracts = []
    try:
        # Parser avec encodage ISO-8859-1
        root = ET.fromstring(xml_content.decode(XML_ENCODING))
        
        # Détecter le namespace automatiquement
        namespace = root.tag.split('}')[0].strip('{') if '}' in root.tag else ''
        
        # Chercher les Assignment de manière agnostique au namespace
        assignments = root.findall(".//*[local-name()='Assignment']")
        
        if not assignments:
            st.error("Aucun contrat (Assignment) trouvé dans le fichier XML")
            st.info(f"Namespace détecté: {namespace or 'aucun'}")
            return []
        
        st.info(f"✅ {len(assignments)} contrat(s) trouvé(s) - Namespace: {namespace or 'aucun'}")
        
        for assignment_elem in assignments:
            contract = ContractData()
            contract.filename = filename
            contract.original_tree = ET.ElementTree(root)
            
            # AssignmentId - chercher IdValue dans la structure HR-XML 2.x
            assignment_id_elem = assignment_elem.find(".//*[local-name()='AssignmentId']")
            if assignment_id_elem is not None:
                # Pour HR-XML 2.x, l'ID est dans IdValue
                id_value_elem = assignment_id_elem.find(".//*[local-name()='IdValue']")
                if id_value_elem is not None and id_value_elem.text:
                    contract.assignment_id = id_value_elem.text.strip()
                # Si pas de IdValue, essayer le texte direct (HR-XML 3.x)
                elif assignment_id_elem.text:
                    contract.assignment_id = assignment_id_elem.text.strip()
            
            # StaffingSupplierId - peut être absent dans HR-XML 2.x
            supplier_elem = assignment_elem.find(".//*[local-name()='StaffingSupplierId']")
            if supplier_elem is not None and supplier_elem.text:
                contract.staffing_supplier_id = supplier_elem.text.strip()
            
            # Extraire les dates - chercher AssignmentDateRange
            date_range_elem = assignment_elem.find(".//*[local-name()='AssignmentDateRange']")
            if date_range_elem is not None:
                # StartDate
                start_elem = date_range_elem.find(".//*[local-name()='StartDate']")
                if start_elem is not None and start_elem.text:
                    try:
                        contract.start_date = parse_date(start_elem.text.strip())
                    except:
                        st.warning(f"Date de début invalide: {start_elem.text}")
                
                # ExpectedEndDate
                expected_end_elem = date_range_elem.find(".//*[local-name()='ExpectedEndDate']")
                if expected_end_elem is not None and expected_end_elem.text:
                    try:
                        contract.expected_end_date = parse_date(expected_end_elem.text.strip())
                    except:
                        st.warning(f"Date de fin prévue invalide: {expected_end_elem.text}")
                
                # ActualEndDate (optionnel)
                actual_end_elem = date_range_elem.find(".//*[local-name()='ActualEndDate']")
                if actual_end_elem is not None and actual_end_elem.text:
                    try:
                        contract.actual_end_date = parse_date(actual_end_elem.text.strip())
                    except:
                        st.warning(f"Date de fin réelle invalide: {actual_end_elem.text}")
                
                # Dates de flexibilité existantes (pour info)
                flex_min_elem = date_range_elem.find(".//*[local-name()='FlexibilityMinDate']")
                if flex_min_elem is not None and flex_min_elem.text:
                    st.info(f"FlexibilityMinDate existante: {flex_min_elem.text.strip()}")
                
                flex_max_elem = date_range_elem.find(".//*[local-name()='FlexibilityMaxDate']")
                if flex_max_elem is not None and flex_max_elem.text:
                    st.info(f"FlexibilityMaxDate existante: {flex_max_elem.text.strip()}")
            
            # TOUJOURS recalculer les dates de flexibilité selon les règles Pilott
            if contract.start_date and contract.expected_end_date:
                flex_min, flex_max, _ = calc_flex_range(
                    contract.start_date, 
                    contract.expected_end_date
                )
                contract.flex_min_date = flex_min
                contract.flex_max_date = flex_max
                contracts.append(contract)
                st.success(f"✅ Contrat {contract.assignment_id or f'#{len(contracts)}'}: Dates recalculées")
            else:
                st.warning(f"⚠️ Contrat {contract.assignment_id or 'sans ID'}: Dates de début/fin manquantes")
        
        return contracts
        
    except ET.ParseError as e:
        st.error(f"Erreur de parsing XML: {str(e)}")
        return []
    except Exception as e:
        st.error(f"Erreur lors du traitement: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return []

def build_au_packet(contract: ContractData) -> ET.ElementTree:
    """Construit un paquet AU (AssignmentUpdate) compatible HR-XML 2004-08-02."""
    # Créer la structure pour HR-XML 2.x
    root = ET.Element('Envelope')
    root.set('xmlns', 'http://ns.hr-xml.org/2004-08-02')
    
    # Packet
    packet = ET.SubElement(root, 'Packet')
    
    # AssignmentPacket
    assignment_packet = ET.SubElement(packet, 'AssignmentPacket')
    
    # Assignment avec attributs
    assignment = ET.SubElement(assignment_packet, 'Assignment')
    assignment.set('assignmentStatus', ASSIGNMENT_STATUS_ACTIVE)
    
    # AssignmentId avec structure HR-XML 2.x
    assignment_id_elem = ET.SubElement(assignment, 'AssignmentId')
    assignment_id_elem.set('idOwner', 'RIS')  # Ou autre valeur appropriée
    id_value = ET.SubElement(assignment_id_elem, 'IdValue')
    id_value.text = contract.assignment_id
    
    # Si StaffingSupplierId existe
    if contract.staffing_supplier_id:
        supplier_elem = ET.SubElement(assignment, 'StaffingSupplierId')
        supplier_elem.text = contract.staffing_supplier_id
    
    # AssignmentDateRange
    date_range = ET.SubElement(assignment, 'AssignmentDateRange')
    
    # Dates
    start_elem = ET.SubElement(date_range, 'StartDate')
    start_elem.text = format_date(contract.start_date)
    
    expected_end_elem = ET.SubElement(date_range, 'ExpectedEndDate')
    expected_end_elem.text = format_date(contract.expected_end_date)
    
    if contract.actual_end_date:
        actual_end_elem = ET.SubElement(date_range, 'ActualEndDate')
        actual_end_elem.text = format_date(contract.actual_end_date)
    
    # Dates de flexibilité recalculées
    flex_min_elem = ET.SubElement(date_range, 'FlexibilityMinDate')
    if contract.flex_min_date:
        flex_min_elem.text = format_date(contract.flex_min_date)
    
    flex_max_elem = ET.SubElement(date_range, 'FlexibilityMaxDate')
    if contract.flex_max_date:
        flex_max_elem.text = format_date(contract.flex_max_date)
    
    return ET.ElementTree(root)

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

def generate_output_filename(file_type: str = 'AU') -> str:
    """Génère un nom de fichier de sortie avec timestamp."""
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    if file_type == 'SA':
        return STAFFING_ACTION_PATTERN.format(timestamp=timestamp)
    else:
        return OUTPUT_FILE_PATTERN.format(timestamp=timestamp)

def tree_to_string(tree: ET.ElementTree, encoding: str = XML_ENCODING) -> bytes:
    """Convertit un ElementTree en bytes avec l'encodage spécifié."""
    _indent(tree.getroot())
    
    # Créer un buffer pour écrire le XML
    buffer = io.BytesIO()
    tree.write(buffer, encoding=encoding, xml_declaration=True, method='xml')
    return buffer.getvalue()

# ============= STREAMLIT APP =============

# Titre principal
st.title("🔧 Pilott Date Editor")
st.markdown("**Calculateur automatique de dates pour contrats HR-XML selon les règles Pilott**")

# État de session
if 'contracts' not in st.session_state:
    st.session_state.contracts = []

# Zone de chargement de fichier
st.header("📁 1. Charger votre fichier XML")
uploaded_file = st.file_uploader(
    "Sélectionnez un fichier XML de contrat",
    type=['xml'],
    help="Format attendu: ASS_*_A_ETT.xml"
)

if uploaded_file is not None:
    # Validation du nom de fichier
    if not re.match(INPUT_FILE_PATTERN, uploaded_file.name):
        st.error(f"❌ {ERROR_MESSAGES['invalid_file_format']}")
    else:
        # Bouton pour analyser le fichier
        if st.button("📊 Analyser le fichier", type="primary"):
            try:
                content = uploaded_file.read()
                contracts = parse_contract_xml(content, uploaded_file.name)
                
                if contracts:
                    st.session_state.contracts = contracts
                    st.success(f"✅ {len(contracts)} contrat(s) trouvé(s) et analysé(s)")
                else:
                    st.error("Aucun contrat valide trouvé dans le fichier")
                    
            except Exception as e:
                st.error(f"Erreur lors du traitement: {str(e)}")

# Affichage et édition des contrats
if st.session_state.contracts:
    st.header("📊 2. Vérifier et modifier les dates")
    
    for idx, contract in enumerate(st.session_state.contracts):
        st.markdown(f"### Contrat {idx + 1} - ID: {contract.assignment_id}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Dates principales**")
            
            # Affichage des dates actuelles
            st.write(f"Date début: **{format_date(contract.start_date)}**")
            st.write(f"Date fin prévue: **{format_date(contract.expected_end_date)}**")
            
            if contract.actual_end_date:
                st.write(f"Date fin réelle: **{format_date(contract.actual_end_date)}**")
            
            # Durée
            if contract.start_date and contract.expected_end_date:
                duration = (contract.expected_end_date - contract.start_date).days + 1
                st.write(f"Durée: **{duration} jours**")
        
        with col2:
            st.markdown("**Dates de flexibilité calculées**")
            
            if contract.flex_min_date and contract.flex_max_date:
                st.success(f"Min: **{format_date(contract.flex_min_date)}**")
                st.success(f"Max: **{format_date(contract.flex_max_date)}**")
                
                # Calcul du nombre de jours
                flex_days = (contract.flex_max_date - contract.expected_end_date).days
                st.info(f"Flexibilité: **{flex_days} jours**")
                
                # Afficher la formule
                duration = (contract.expected_end_date - contract.start_date).days + 1
                calculated = min(10, max(1, duration // 5))
                st.caption(f"Calcul: ⌊{duration}/5⌋ = {calculated} jours")
        
        with col3:
            st.markdown("**Validation**")
            
            # Validation
            valid, error_msg = validate_date_coherence(
                contract.start_date,
                contract.expected_end_date,
                contract.actual_end_date
            )
            
            if valid:
                st.success("✅ Dates cohérentes")
            else:
                st.error(f"❌ {error_msg}")
        
        st.divider()
    
    # Section de génération
    st.header("📄 3. Générer les fichiers de mise à jour")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚀 Générer les fichiers AU", type="primary", use_container_width=True):
            for idx, contract in enumerate(st.session_state.contracts):
                try:
                    # Générer le fichier AU
                    au_tree = build_au_packet(contract)
                    xml_content = tree_to_string(au_tree)
                    filename = generate_output_filename('AU')
                    
                    # Bouton de téléchargement
                    st.download_button(
                        label=f"📥 Télécharger {filename}",
                        data=xml_content,
                        file_name=filename,
                        mime="application/xml",
                        key=f"download_{idx}"
                    )
                    
                except Exception as e:
                    st.error(f"Erreur génération contrat {idx + 1}: {str(e)}")
    
    with col2:
        if st.button("🗑️ Réinitialiser", use_container_width=True):
            st.session_state.contracts = []
            st.rerun()

else:
    # Instructions si aucun fichier chargé
    st.info("👆 Chargez un fichier XML pour commencer")
    
    with st.expander("📖 Guide d'utilisation"):
        st.markdown("""
        ### Comment utiliser cette application
        
        1. **Chargez votre fichier XML** (format: ASS_*_A_ETT.xml)
        2. **Cliquez sur "Analyser"** pour extraire les contrats
        3. **Vérifiez les dates** calculées automatiquement
        4. **Générez les fichiers AU** avec les dates corrigées
        
        ### Règles de calcul appliquées
        
        - **Jours de flexibilité** = ⌊(durée en jours / 5)⌋
        - **Minimum**: 1 jour
        - **Maximum**: 10 jours
        - **FlexibilityMinDate** = ExpectedEndDate - jours de flexibilité
        - **FlexibilityMaxDate** = ExpectedEndDate + jours de flexibilité
        
        ### Format des dates
        
        Toutes les dates sont au format **YYYY-MM-DD** (ISO 8601)
        """)

# Footer
st.markdown("---")
st.caption("Pilott Date Editor v1.0 - Calcul automatique des dates de flexibilité")
