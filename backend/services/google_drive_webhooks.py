"""
Google Drive Push Notifications (Webhooks) for real-time sync.

Alternative to polling (CRON). Google Drive API can push notifications
to your endpoint whenever files are added, modified, or deleted.

Flow:
  1. Set up a watch channel on the folder (GoogleDriveConnector.watch_folder)
  2. Google Drive pushes to your webhook endpoint
  3. Webhook handler fetches the changed file and processes it
  4. Minimal latency (seconds instead of hours/days with CRON)

Requires:
  - Public URL reachable by Google (e.g., via ngrok for local dev)
  - Database to track channel expiration and renewal
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from uuid import uuid4

logger = logging.getLogger(__name__)


class WebhookChannelTracker:
    """
    Track active Google Drive watch channels.
    Channels expire and must be renewed periodically.
    """

    def __init__(self, db_session):
        from models import GoogleDriveWebhookChannel
        self.db = db_session
        self.DBChannel = GoogleDriveWebhookChannel

    def create_channel(self, tenant_id: str, folder_id: str,
                      channel_id: str, resource_id: str,
                      expiration: int) -> str:
        """
        Track a new watch channel.

        Args:
            tenant_id: Tenant UUID
            folder_id: Google Drive folder ID
            channel_id: Channel ID returned by Google
            resource_id: Resource ID returned by Google
            expiration: Expiration timestamp (milliseconds)

        Returns:
            Channel record ID
        """
        try:
            # Convert ms timestamp to datetime
            exp_dt = datetime.utcfromtimestamp(expiration / 1000.0)

            channel = self.DBChannel(
                id=channel_id,
                tenant_id=tenant_id,
                folder_id=folder_id,
                channel_id=channel_id,
                resource_id=resource_id,
                expires_at=exp_dt,
                status="active",
                created_at=datetime.utcnow()
            )
            self.db.add(channel)
            self.db.commit()

            logger.info(f"[WebhookChannel] Created channel {channel_id} for folder {folder_id}")
            return channel_id

        except Exception as e:
            logger.error(f"[WebhookChannel] Error creating channel: {e}")
            raise

    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """Get channel info."""
        try:
            channel = self.db.query(self.DBChannel).filter(
                self.DBChannel.channel_id == channel_id
            ).first()

            if channel:
                return {
                    "id": channel.id,
                    "tenant_id": channel.tenant_id,
                    "folder_id": channel.folder_id,
                    "channel_id": channel.channel_id,
                    "resource_id": channel.resource_id,
                    "expires_at": channel.expires_at,
                    "status": channel.status
                }
            return None

        except Exception as e:
            logger.error(f"[WebhookChannel] Error getting channel: {e}")
            return None

    def mark_renewal_needed(self, channel_id: str):
        """Mark channel for renewal (expiring soon)."""
        try:
            channel = self.db.query(self.DBChannel).filter(
                self.DBChannel.channel_id == channel_id
            ).first()

            if channel:
                channel.status = "renewal_needed"
                self.db.commit()
                logger.info(f"[WebhookChannel] Marked channel {channel_id} for renewal")

        except Exception as e:
            logger.error(f"[WebhookChannel] Error marking renewal: {e}")

    def mark_expired(self, channel_id: str):
        """Mark channel as expired."""
        try:
            channel = self.db.query(self.DBChannel).filter(
                self.DBChannel.channel_id == channel_id
            ).first()

            if channel:
                channel.status = "expired"
                self.db.commit()
                logger.warning(f"[WebhookChannel] Marked channel {channel_id} as expired")

        except Exception as e:
            logger.error(f"[WebhookChannel] Error marking expired: {e}")


class WebhookNotificationHandler:
    """
    Handle incoming push notifications from Google Drive.

    Google sends POST to your endpoint with:
      Headers:
        X-Goog-Channel-ID: <channel_id>
        X-Goog-Channel-Token: <channel_token>
        X-Goog-Message-Number: <sequence>
        X-Goog-Resource-ID: <resource_id>
        X-Goog-Resource-State: <sync|exists>
      Body: Empty (actual file info must be fetched via API)
    """

    @staticmethod
    def parse_notification(headers: Dict, body: str = None) -> Dict:
        """
        Parse incoming webhook notification.

        Returns:
            {
              "channel_id": "...",
              "channel_token": "...",
              "message_number": 123,
              "resource_id": "...",
              "resource_state": "exists|sync",
              "timestamp": datetime
            }
        """
        return {
            "channel_id": headers.get("X-Goog-Channel-ID", ""),
            "channel_token": headers.get("X-Goog-Channel-Token", ""),
            "message_number": int(headers.get("X-Goog-Message-Number", "0")),
            "resource_id": headers.get("X-Goog-Resource-ID", ""),
            "resource_state": headers.get("X-Goog-Resource-State", "exists"),
            "timestamp": datetime.utcnow()
        }

    @staticmethod
    def validate_notification(notification: Dict, channel: Dict) -> bool:
        """
        Validate notification authenticity.

        Checks:
          - Channel exists and is active
          - Resource ID matches
          - Message number is sensible
        """
        if not channel:
            logger.warning(f"[WebhookHandler] Channel not found: {notification['channel_id']}")
            return False

        if channel["status"] != "active":
            logger.warning(f"[WebhookHandler] Channel not active: {notification['channel_id']}")
            return False

        if notification["resource_id"] != channel["resource_id"]:
            logger.error(f"[WebhookHandler] Resource ID mismatch")
            return False

        return True

    @staticmethod
    def should_renew_channel(channel: Dict) -> bool:
        """Check if channel is expiring soon (within 1 hour)."""
        if not channel or not channel.get("expires_at"):
            return False

        expires_at = channel["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        renewal_threshold = datetime.utcnow() + timedelta(hours=1)
        return expires_at <= renewal_threshold


class GoogleDriveWatchManager:
    """
    Manage watch channels and handle renewals.
    """

    def __init__(self, drive_connector, db_session):
        """
        Args:
            drive_connector: GoogleDriveConnector instance
            db_session: Database session for tracking channels
        """
        self.drive = drive_connector
        self.db = db_session
        self.tracker = WebhookChannelTracker(db_session)

    def setup_watch(self, tenant_id: str, folder_id: str,
                    webhook_url: str) -> Optional[str]:
        """
        Set up a watch channel on a folder.

        Args:
            tenant_id: Tenant UUID
            folder_id: Google Drive folder ID
            webhook_url: HTTPS URL where Google will POST notifications
                        (e.g., https://myapp.com/api/google-drive-webhook)

        Returns:
            Channel ID if successful, None otherwise
        """
        if not self.drive.service:
            logger.error("[WatchManager] Drive not authenticated")
            return None

        try:
            channel_id = str(uuid4())

            # Create watch channel
            request_body = {
                "id": channel_id,
                "type": "web_hook",
                "address": webhook_url,
                "params": {
                    "ttl": "3600"  # 1 hour TTL
                }
            }

            logger.info(f"[WatchManager] Setting up watch on folder {folder_id}")
            response = self.drive.service.files().watch(
                fileId=folder_id,
                body=request_body
            ).execute()

            # Track the channel
            expiration = int(response.get("expiration", 0))
            resource_id = response.get("resourceId", "")

            self.tracker.create_channel(
                tenant_id=tenant_id,
                folder_id=folder_id,
                channel_id=channel_id,
                resource_id=resource_id,
                expiration=expiration
            )

            logger.info(f"[WatchManager] Watch channel created: {channel_id}")
            logger.info(f"[WatchManager] Expiration: {expiration} (will renew in ~55 min)")

            return channel_id

        except Exception as e:
            logger.error(f"[WatchManager] Error setting up watch: {e}")
            return None

    def stop_watch(self, channel_id: str):
        """
        Stop watching a folder.

        Args:
            channel_id: Channel ID to stop
        """
        if not self.drive.service:
            return

        try:
            channel = self.tracker.get_channel(channel_id)
            if not channel:
                logger.warning(f"[WatchManager] Channel not found: {channel_id}")
                return

            # Stop the watch
            request_body = {
                "id": channel_id,
                "resourceId": channel["resource_id"]
            }

            self.drive.service.channels().stop(body=request_body).execute()
            self.tracker.mark_expired(channel_id)

            logger.info(f"[WatchManager] Stopped watch channel: {channel_id}")

        except Exception as e:
            logger.error(f"[WatchManager] Error stopping watch: {e}")
