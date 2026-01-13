# ERP Automated Reporting & OS Features Guide

This document outlines the advanced automation and "OS-level" functionality integrated into the Supply Chain Management ERP.

## 1. Automated Reporting System

### Weekly Business Health Digest
*   **Trigger**: Every Monday at 00:00 (via Celery Beat).
*   **Logic**: 
    - **Scalability**: Uses a "Fan-out" pattern. A coordinator task spawns individual sub-tasks for each owner, ensuring that one failure doesn't stop other reports.
    - **Robust Reporting**: Generates a professional PDF using `reportlab` Tables and Paragraphs.
*   **Delivery**: 
    - Saved to `WeeklyBusinessHealthDigest` model.
    - In-app notification sent with a generic link to the digest record.

### Predictive Inventory Monitor
*   **Trigger**: Daily task.
*   **Anti-Spam Logic**: Remembers if an alert was sent for a specific product in the last 24 hours to avoid "Alert Fatigue".
*   **Action**: Sends a system-level Push Notification only for new or persistent low-stock issues.

## 2. ERP Intelligence (Data Science)

### Customer RFM Segmentation (Smart Scoring)
*   **Dynamic Quintiles**: Unlike simple fixed-threshold reporting, this system uses **Pandas** to calculate quintiles (20% groupings) *specifically for each shop owner's dataset*.
*   **Recency (R)**: 5 (recent) to 1 (long time ago).
*   **Frequency (F)**: 5 (many orders) to 1 (one-off).
*   **Monetary (M)**: 5 (high spend) to 1 (low spend).
*   **Performance**: Processed via Celery groups for horizontal scaling.

### Lost Sales Analysis
*   **Calculation**: `Avg Daily Demand` × `Days Out of Stock` × `Price`.
*   **Purpose**: Quantifies the financial impact of supply chain delays or inventory mismanagement.

## 3. OS-style Interface Features

### Global Command Palette (Spotlight Search)
*   **Endpoint**: `GET /api/v1/reports/palette/`
*   **Function**: Returns a list of context-aware commands (shortcuts) for the frontend to render in a search bar.
*   **Shortcuts included**: 
    - `Ctrl+P`: Search Products.
    - `Ctrl+E`: Export Sales.
    - `Ctrl+I`: Inventory Audit.

### Task status (System Health)
*   Provides status indicators for the ERP's internal motors (Celery workers, database health, etc.).

## 4. Technical Implementation Details

### Models Added
- [report/models.py](report/models.py#L46): `WeeklyBusinessHealthDigest` (Stores weekly snapshots).
- [report/models.py](report/models.py#L76): `CustomerRFMSegment` (Stores RFM scores).

### Tasks Added
- `generate_weekly_business_digests`: Weekly aggregation.
- `check_inventory_and_alert`: Predictive alerting.
- `automated_rfm_segmentation`: Intelligence update.

### Setup Instructions
1. Ensure Celery workers are running.
2. Run migrations: `python manage.py migrate report`.
3. Add the tasks to `CELERY_BEAT_SCHEDULE` in `main/settings.py` (or via Django Admin).
