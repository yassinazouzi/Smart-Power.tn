# 📈 SmartPower SaaS — Modèle d'Affaires & Feuille de Route Tunisie (TND)
> **Stratégie de Commercialisation, Monétisation et Tarification en Dinars Tunisiens (DT / TND)**

---

## 1. Modèle de Monétisation en Tunisie (Hardware + SaaS)

En Tunisie, le marché de la domotique et de l'efficacité énergétique est en pleine explosion, poussé par les hausses régulières des tarifs de l'électricité (**STEG**).

```
                  ┌────────────────────────────────────────┐
                  │       VENTE DE MATÉRIEL (HARDWARE)     │
                  │  Boîtiers Switch & Prises intelligentes│
                  │  Marge brute : 50% à 65%               │
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
                  ┌────────────────────────────────────────┐
                  │      ABONNEMENTS RÉCURRENTS (SaaS)     │
                  │   Paiement annuel ou mensuel en TND    │
                  │   Flouci, Konnect, ClicToPay, Sobflous │
                  └────────────────────────────────────────┘
```

---

## 2. Grille Tarifaire SaaS (en Dinars Tunisiens)

| Formule | Cible | Tarif en Dinars Tunisiens | Fonctionnalités Incluses |
| :--- | :--- | :--- | :--- |
| **Gratuit (Free)** | Particuliers (Studio / Petit Appartement) | **0 DT / mois** *(À vie)* | Jusqu'à 4 appareils, contrôle à distance sans fil, historique énergie 7 jours, 3 scénarios automatisés. |
| **Smart Home Pro** | Particuliers & Villas | **9.900 DT / mois** *(ou 99 DT / an)* | • Appareils illimités<br>• Historique énergie 2 ans<br>• **Calculateur de facture STEG en direct**<br>• **Alerte anti-dépassement de palier STEG** (Notification SMS/Push avant de basculer sur le tarif le plus cher)<br>• Scénarios illimités (Extinction clim automatique si fenêtre ouverte)<br>• Partage familial illimité. |
| **Smart Business / Hôtels** | Hôtels, Cafés, Coworking, PME, Usines | **49.000 DT / mois** *(+ 3 DT/boîtier au-delà de 10)* | • Multi-bâtiments & multi-chambres<br>• Coupure automatique des climatiseurs si la chambre est inoccupée<br>• Suivi de puissance maximale (évite les pénalités de dépassement de puissance souscrite STEG)<br>• Export comptable et audit d'efficacité énergétique<br>• Tableau de bord administrateur & sous-comptes techniciens. |

---

## 3. Nomenclature Matérielle (BOM) & Prix de Vente en Tunisie

Pour fabriquer un module Switch intelligent ou Prise connectée SmartPower :

| Composant | Coût Estimé (Import/Gros) | Coût en Dinars (TND) |
| :--- | :--- | :--- |
| **Microcontrôleur ESP32-WROOM / ESP32-C3** | ~ $1.80 | ~ 5.600 DT |
| **Module Alimentation AC/DC (220V vers 5V) Hi-Link** | ~ $1.30 | ~ 4.000 DT |
| **Relais 16A 250V AC de qualité industrielle** | ~ $0.50 | ~ 1.550 DT |
| **PCB imprimé double face + composants passifs** | ~ $0.60 | ~ 1.850 DT |
| **Boîtier ABS ignifugé avec borniers à vis** | ~ $0.70 | ~ 2.150 DT |
| **Packaging & Sticker QR Code d'appairage** | ~ $0.30 | ~ 0.950 DT |
| **Coût de Revient Total Produit Fini :** | **~ $5.20** | **~ 16.100 DT** |

### Prix de Vente Public Recommandé en Tunisie :
- **Smart Switch 1-Canal (Relais éclairage encastrable)** : **45.000 DT TTC** *(Marge brute : ~29 DT par pièce)*
- **Smart Switch 4-Canaux (Tableau électrique)** : **89.000 DT TTC** *(Marge brute : ~55 DT par pièce)*
- **Smart Plug avec Mesure d'Énergie instantanée (Prise)** : **59.000 DT TTC** *(Marge brute : ~38 DT par pièce)*

---

## 4. Intégration des Paliers Tarifaires STEG (Argument Vente Majeur)

En Tunisie, la STEG applique une tarification progressive par paliers de consommation mensuelle :

| Palier STEG (Basse Tension Résidentielle) | Tranche Mensuelle (kWh) | Prix au kWh (DT) |
| :--- | :---: | :---: |
| **Palier 1 (Économique)** | 1 à 200 kWh | **0.181 DT** |
| **Palier 2 (Moyen)** | 201 à 300 kWh | **0.223 DT** *(+23%)* |
| **Palier 3 (Confort)** | 301 à 500 kWh | **0.338 DT** *(+51%)* |
| **Palier 4 (Fort / Climatisation intense)** | Au-delà de 500 kWh | **0.419 DT** *(+88%)* |

### L'avantage concurrentiel SmartPower :
L'application prédit le franchissement de palier en milieu de mois et alerte l'utilisateur :
> *"⚠️ Attention : Votre foyer a consommé 190 kWh au 18 du mois. Si vous continuez à ce rythme, vos 100 prochains kWh seront facturés à 0.223 DT au lieu de 0.181 DT. Cliquez ici pour activer le mode Éco."*

---

## 5. Canaux de Paiement SaaS en Tunisie

Pour faciliter l'encaissement des abonnements récurrents en Tunisie :
1. **Flouci Gateway** (Paiement par QR Code et virement instantané via l'application Flouci).
2. **Konnect Network** (Cartes bancaires nationales CIB, e-Dinar La Poste Tunisienne, Visa/Mastercard).
3. **ClicToPay / Monétique Tunisie (SMT)** (Paiement direct bancaire).
4. **Sobflous** (Recharges de wallet et cartes cadeaux).
