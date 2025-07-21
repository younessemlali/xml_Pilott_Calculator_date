# 🔧 Pilott Date Editor

Application Streamlit pour l'édition et la correction automatique des dates dans les contrats HR-XML selon les règles métier Pilott.

## 🚀 Installation rapide

```bash
git clone https://github.com/your-org/pilott_date_editor.git
cd pilott_date_editor
pip install -r requirements.txt
streamlit run app.py
```

## 📋 Fonctionnalités principales

- **Chargement multi-fichiers** : Glissez-déposez vos fichiers XML (format ASS_*_A_ETT.xml)
- **Calcul automatique** : Les dates de flexibilité sont recalculées selon la règle ⌊(durée/5)⌋, max 10 jours
- **Validation en temps réel** : Alertes visuelles pour les incohérences de dates
- **Génération AU/SA** : Création automatique des fichiers de mise à jour conformes
- **Support ISO-8859-1** : Gestion native de l'encodage des fichiers RH français

## 📁 Structure du projet

```
pilott_date_editor/
├── app.py                    # Application Streamlit principale
├── pilott_editor/
│   ├── __init__.py
│   ├── constants.py          # Constantes et configuration
│   ├── date_calc.py          # Logique métier des dates
│   └── xml_utils.py          # Parsing et génération XML
├── examples/
│   └── ASS_20250121_A_ETT.xml  # Contrat exemple
├── tests/
│   └── test_date_calc.py     # Tests unitaires
└── resources/xsd/            # Schémas XSD (à ajouter)
```

## 🧪 Scénario de test

### 1. Préparation
- Lancez l'application : `streamlit run app.py`
- Utilisez le fichier exemple dans `examples/ASS_20250121_A_ETT.xml`

### 2. Chargement
- Cliquez sur "Browse files" dans la barre latérale
- Sélectionnez le fichier exemple
- Cliquez sur "🔄 Charger les fichiers"

### 3. Édition
- Dans l'onglet "📊 Édition des dates" :
  - Modifiez la date de fin prévue au 2025-04-30
  - Observez le recalcul automatique des dates de flexibilité (10 jours)
  - Les nouvelles dates seront : Min: 2025-04-20, Max: 2025-05-10

### 4. Génération
- Allez dans l'onglet "📄 Génération AU"
- Sélectionnez "AU (Mise à jour)"
- Cliquez sur "🚀 Générer les fichiers"
- Téléchargez le fichier AU généré

### 5. Validation
Le fichier généré contiendra :
- `processStatus="update"` et `assignmentStatus="active"`
- Les dates mises à jour avec les nouvelles valeurs
- Un nouveau `transactId` UUID et `timeStamp` actuel

## 🛠️ Configuration avancée

### Variables d'environnement (optionnel)
```bash
export PILOTT_XSD_PATH=/path/to/xsd/files
export PILOTT_DEFAULT_TIMEZONE=Europe/Paris
```

### Validation XSD
Placez vos fichiers XSD dans le dossier `resources/xsd/`. L'application validera automatiquement les XML générés si les schémas sont présents.

## 📝 Règles métier implémentées

1. **Calcul de flexibilité** : 
   - Nombre de jours = ⌊(durée calendaire / 5)⌋
   - Minimum : 1 jour
   - Maximum : 10 jours

2. **Contraintes de dates** :
   - StartDate < ExpectedEndDate
   - ActualEndDate ≤ FlexibilityMaxDate
   - FlexibilityMinDate = ExpectedEndDate - n jours
   - FlexibilityMaxDate = ExpectedEndDate + n jours

3. **Formats** :
   - Dates : YYYY-MM-DD
   - Horodatages : YYYY-MM-DDThh:mm:ssZ (UTC)
   - Encodage XML : ISO-8859-1

## 🐛 Dépannage

### Erreur "Date souplesse incohérente"
Vérifiez que la date de fin réelle est comprise entre FlexibilityMinDate et FlexibilityMaxDate.

### Erreur "Identification contrat impossible"
Assurez-vous que l'AssignmentId et StaffingSupplierId correspondent exactement au contrat initial.

### Problèmes d'encodage
Les fichiers doivent être en ISO-8859-1. L'application gère automatiquement la conversion.

## 📧 Support

Pour toute question ou problème, contactez l'équipe Pilott Development.
