# SmartPower.tn ⚡ — IoT Smart Home SaaS Platform

SmartPower est une plateforme SaaS IoT complète conçue pour la gestion domotique intelligente, le suivi énergétique en temps réel et le contrôle d'équipements connectés (ESP32, Sonoff, etc.).

---

## 🏗️ Architecture du Projet

```text
SmartPower/
├── dashboard/               # Plateforme SaaS Web & API Flask
│   ├── app.py               # Serveur Flask, synchronisation ESP32 & endpoints REST
│   ├── mysql_manager.py     # Couche de persistance MySQL multi-tenant
│   └── templates/
│       └── index.html       # Interface UI avec Three.js (Vue 3D Isométrique) & Studio Caméra
├── firmware/                # Codes sources pour microcontrôleurs
│   ├── esp32_smartpower_dashboard/ # Firmware complet ESP32 (HTTP REST, mDNS, GPIO)
│   └── esp32-switch/               # Firmware interrupteur connecté
├── docs/                    # Spécifications & Architecture
│   ├── SAAS_ARCHITECTURE.md
│   ├── SAAS_BUSINESS_ROADMAP.md
│   └── DEVICE_PROTOCOL_SPEC.md
└── tools/                   # Utilitaires de compilation et de flash
    ├── update_sketch.py
    └── upgrade_sketch_sonoff.py
```

---

## 🌟 Fonctionnalités Clés

1. **Tableau de Bord SaaS Multi-Tenant :**
   - Suivi énergétique temps réel (Puissance active, tension 230V, intensité, consommation kWh).
   - Gestion des utilisateurs et matrice d'affectation dynamique des droits d'accès aux équipements.
   - Synchronisation bidirectionnelle MySQL (`sp_devices`, `sp_users`, `sp_access`, `sp_scenes`, `sp_telemetry`).

2. **Jumeau Numérique 3D Interactif :**
   - Visualisation d'appartement en 3D Isométrique via **Three.js** avec rendu photoréaliste ACES Filmic et ombres douces.
   - Presets de caméra (Isométrique, Salon, Chambre, Cuisine, Entrée, Plan 2D).
   - Pins 3D interactifs géoréférencés sur les équipements physiques.
   - Raycasting 3D pour basculer les relais physiques en cliquant sur le mobilier.
   - Robot aspirateur patrouilleur animé en temps réel.
   - Ambiance Nuit / Jour et mode Auto-Tour turntable.

3. **Studio Caméra de Sécurité & Badge Dynamique :**
   - Badge compact glassmorphic et carte de flux en direct.
   - Moniteur de surveillance 16:9, Vision Nocturne IR et détection d'intrus.
   - Contrôle PTZ interactif, Interphone audio avec animation de signal et sirène d'alerte 105 dB.

4. **Synchronisation Matérielle ESP32 :**
   - Détection automatique et handshake via USB COM et Wi-Fi mDNS (`smartpower-esp32.local`).
   - Configuration Wi-Fi / provisioning direct depuis l'interface web.
   - Détection instantanée des déconnexions physiques avec mise à jour du statut dans MySQL.

---

## 🚀 Démarrage Rapide

### 1. Prérequis
- Python 3.10+
- Serveur MySQL (ex. WampServer / XAMPP ou MySQL Server)
- Microcontrôleur ESP32 (optionnel pour la simulation)

### 2. Configuration MySQL
Importez les tables ou laissez l'initialisation automatique via `dashboard/mysql_manager.py` :
```sql
CREATE DATABASE IF NOT EXISTS smartpower_dev CHARACTER SET utf8mb4;
```

### 3. Lancer le Tableau de Bord
```bash
cd dashboard
pip install flask pyserial requests mysql-connector-python
python app.py
```
Le tableau de bord est alors accessible sur :
- Local : [http://localhost:8080](http://localhost:8080)
- Réseau local : `http://<VOTRE_IP_LOCALE>:8080`

---

## 📄 Licence
Propriété exclusive de SmartPower Tunisie. Tous droits réservés.
