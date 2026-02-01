"""
Celery tasks for bulk import/export operations
"""

import logging
from typing import Optional

from celery import shared_task
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .bulk_operations import (
    ImportResult,
    ProductExporter,
    ProductImporter,
    get_import_progress,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def import_products_csv_task(self, file_content: str, user_id: int, job_id: str, update_existing: bool = True):
    """
    Celery task to import products from CSV.

    Args:
        file_content: CSV file content as string
        user_id: ID of the user performing the import
        job_id: Unique job identifier
        update_existing: Whether to update existing products
    """
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        importer = ProductImporter(user, update_existing=update_existing)

        # Set initial status
        cache.set(
            f"import_progress_{job_id}",
            {"job_id": job_id, "status": "started", "processed": 0, "total": 0, "percent": 0},
            3600,
        )

        # Perform import
        result = importer.import_csv(file_content, job_id)

        # Cache result
        cache.set(
            f"import_result_{job_id}",
            {
                "job_id": result.job_id,
                "total_rows": result.total_rows,
                "success_count": result.success_count,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "errors": result.errors,
                "created_products": result.created_products,
                "updated_products": result.updated_products,
                "failed_rows": result.failed_rows[:100],  # Limit stored errors
                "started_at": result.started_at.isoformat() if result.started_at else None,
                "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                "status": result.status,
            },
            86400,
        )  # Keep for 24 hours

        # Update final progress
        cache.set(
            f"import_progress_{job_id}",
            {
                "job_id": job_id,
                "status": result.status,
                "processed": result.total_rows,
                "total": result.total_rows,
                "percent": 100,
                "success_count": result.success_count,
                "error_count": result.error_count,
            },
            86400,
        )

        logger.info(f"Import job {job_id} completed: {result.success_count} success, {result.error_count} errors")

        return {
            "job_id": job_id,
            "status": result.status,
            "success_count": result.success_count,
            "error_count": result.error_count,
        }

    except Exception as exc:
        logger.exception(f"Import task failed for job {job_id}")

        # Update status to failed
        cache.set(f"import_progress_{job_id}", {"job_id": job_id, "status": "failed", "error": str(exc)}, 86400)

        # Retry on certain errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)

        raise


@shared_task(bind=True, max_retries=3)
def import_products_excel_task(self, file_content_bytes: bytes, user_id: int, job_id: str, update_existing: bool = True):
    """
    Celery task to import products from Excel.
    """
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        importer = ProductImporter(user, update_existing=update_existing)

        cache.set(
            f"import_progress_{job_id}",
            {"job_id": job_id, "status": "started", "processed": 0, "total": 0, "percent": 0},
            3600,
        )

        result = importer.import_excel(file_content_bytes, job_id)

        cache.set(
            f"import_result_{job_id}",
            {
                "job_id": result.job_id,
                "total_rows": result.total_rows,
                "success_count": result.success_count,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "errors": result.errors,
                "created_products": result.created_products,
                "updated_products": result.updated_products,
                "failed_rows": result.failed_rows[:100],
                "started_at": result.started_at.isoformat() if result.started_at else None,
                "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                "status": result.status,
            },
            86400,
        )

        cache.set(
            f"import_progress_{job_id}",
            {
                "job_id": job_id,
                "status": result.status,
                "processed": result.total_rows,
                "total": result.total_rows,
                "percent": 100,
                "success_count": result.success_count,
                "error_count": result.error_count,
            },
            86400,
        )

        logger.info(f"Excel import job {job_id} completed: {result.success_count} success, {result.error_count} errors")

        return {
            "job_id": job_id,
            "status": result.status,
            "success_count": result.success_count,
            "error_count": result.error_count,
        }

    except Exception as exc:
        logger.exception(f"Excel import task failed for job {job_id}")

        cache.set(f"import_progress_{job_id}", {"job_id": job_id, "status": "failed", "error": str(exc)}, 86400)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)

        raise


@shared_task(bind=True, max_retries=3)
def export_products_task(self, user_id: int, filters: dict, format: str, job_id: str):
    """
    Celery task to export products.

    Args:
        user_id: ID of the user requesting export
        filters: Dict of filters to apply
        format: 'csv' or 'excel'
        job_id: Unique job identifier
    """
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        exporter = ProductExporter(user)

        # Set initial status
        cache.set(f"export_progress_{job_id}", {"job_id": job_id, "status": "processing", "percent": 0}, 3600)

        # Perform export
        if format == "csv":
            filename, content = exporter.export_csv(filters)
            content_bytes = content.encode("utf-8")
        elif format == "excel":
            filename, content_bytes = exporter.export_excel(filters)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # Save to storage
        filepath = f"exports/{user_id}/{job_id}_{filename}"
        saved_path = default_storage.save(filepath, ContentFile(content_bytes))

        # Generate download URL
        download_url = default_storage.url(saved_path)

        # Cache result
        cache.set(
            f"export_result_{job_id}",
            {
                "job_id": job_id,
                "status": "completed",
                "filename": filename,
                "file_path": saved_path,
                "download_url": download_url,
                "format": format,
                "file_size": len(content_bytes),
            },
            86400,
        )

        cache.set(
            f"export_progress_{job_id}",
            {"job_id": job_id, "status": "completed", "percent": 100, "download_url": download_url},
            86400,
        )

        logger.info(f"Export job {job_id} completed: {filename}")

        return {"job_id": job_id, "status": "completed", "filename": filename, "download_url": download_url}

    except Exception as exc:
        logger.exception(f"Export task failed for job {job_id}")

        cache.set(f"export_progress_{job_id}", {"job_id": job_id, "status": "failed", "error": str(exc)}, 86400)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)

        raise


@shared_task
def cleanup_old_export_files():
    """Periodic task to clean up old export files"""
    import os
    from datetime import datetime, timedelta

    from django.conf import settings

    exports_dir = os.path.join(settings.MEDIA_ROOT, "exports")
    if not os.path.exists(exports_dir):
        return

    cutoff_date = datetime.now() - timedelta(days=7)
    deleted_count = 0

    for root, dirs, files in os.walk(exports_dir):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if modified_time < cutoff_date:
                    os.remove(file_path)
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {e}")

    logger.info(f"Cleanup completed: {deleted_count} old export files deleted")
    return {"deleted_count": deleted_count}
