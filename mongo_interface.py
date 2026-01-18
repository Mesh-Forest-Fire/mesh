import os
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Literal
from pymongo import MongoClient, GEOSPHERE
from pymongo.database import Database
from pymongo.collection import Collection
import uuid
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Cached connection
_cached_client: Optional[MongoClient] = None
_cached_db: Optional[Database] = None

MONGODB_URL = os.getenv("MONGODB_URL") or os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB_NAME", "test")


def connect_mongodb() -> Database:
    """
    Connect to MongoDB and return the database instance.
    Caches the connection for reuse.
    """
    global _cached_client, _cached_db
    
    if _cached_db is not None:
        logger.debug("Returning cached MongoDB connection")
        return _cached_db
    
    if not MONGODB_URL:
        logger.error("MONGODB_URL (or MONGODB_URI) is not set in the environment")
        raise ValueError("MONGODB_URL (or MONGODB_URI) is not set in the environment")
    
    logger.info(f"Connecting to MongoDB database: {DB_NAME}")
    try:
        _cached_client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
        _cached_db = _cached_client[DB_NAME]
        
        # Test the connection
        _cached_client.server_info()
        
        # Create indexes
        _setup_indexes(_cached_db)
        
        logger.info(f"Successfully connected to MongoDB database: {DB_NAME}")
        return _cached_db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        _cached_client = None
        _cached_db = None
        raise


def _setup_indexes(db: Database):
    """Create necessary indexes for the incidents collection."""
    logger.info("Setting up MongoDB indexes")
    incidents: Collection = db["incidents"]
    
    # Unique index on incidentId
    incidents.create_index("incidentId", unique=True)
    logger.debug("Created unique index on incidentId")
    
    # Index on status
    incidents.create_index("status")
    logger.debug("Created index on status")
    
    # Geospatial index on location
    incidents.create_index([("location", GEOSPHERE)])
    logger.debug("Created geospatial index on location")
    
    # Index on traversalPath.hopIndex
    incidents.create_index("traversalPath.hopIndex")
    logger.debug("Created index on traversalPath.hopIndex")
    
    logger.info("MongoDB indexes created successfully")


def get_mongodb_connection() -> Database:
    """
    Get the cached MongoDB database connection.
    Auto-connects if not already initialized.
    """
    if _cached_db is None:
        logger.info("MongoDB not initialized, attempting to connect...")
        return connect_mongodb()
    
    logger.debug("Retrieved MongoDB connection")
    return _cached_db


def is_mongodb_available() -> bool:
    """
    Check if MongoDB connection is available.
    Returns True if connected or can connect, False otherwise.
    """
    try:
        if _cached_db is not None:
            return True
        connect_mongodb()
        return True
    except Exception as e:
        logger.warning(f"MongoDB not available: {e}")
        return False


def create_incident(
    incident_type: Literal["fire", "other"],
    severity: int,
    origin_node_id: str,
    detection_method: Literal["sensor", "ai"],
    coordinates: tuple[float, float],  # (lng, lat)
    region_code: str,
    base_node_id: str,
    summary: str,
    status: Literal["open", "in_progress", "resolved", "archived"] = "open",
    location_description: Optional[str] = None,
    raw_data: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[str]] = None,
    incident_id: Optional[str] = None
) -> str:
    """
    Create a new incident in MongoDB.
    
    Args:
        incident_type: Type of incident ("fire" or "other")
        severity: Severity level (1-10)
        origin_node_id: ID of the node that first detected the incident
        detection_method: How the incident was detected ("sensor" or "ai")
        coordinates: Tuple of (longitude, latitude)
        region_code: Region code for the location
        base_node_id: ID of the base station receiving the incident
        summary: Summary description of the incident
        status: Current status (default: "open")
        location_description: Optional description of the location
        raw_data: Optional raw sensor/detection data
        attachments: Optional list of attachment URLs/paths
        incident_id: Optional custom incident ID (auto-generated if not provided)
    
    Returns:
        str: The incident ID
    """
    db = get_mongodb_connection()
    incidents: Collection = db["incidents"]
    
    if incident_id is None:
        incident_id = str(uuid.uuid4())
    
    now = datetime.utcnow()
    
    incident_doc = {
        "incidentId": incident_id,
        "type": incident_type,
        "severity": max(1, min(10, severity)),  # Clamp between 1-10
        "status": status,
        "source": {
            "originNodeId": origin_node_id,
            "detectionMethod": detection_method,
            "detectedAt": now
        },
        "location": {
            "type": "Point",
            "coordinates": list(coordinates),  # [lng, lat]
            "regionCode": region_code
        },
        "traversalPath": [],
        "baseReceipt": {
            "baseNodeId": base_node_id,
            "receivedAt": now,
            "processingStatus": "queued"
        },
        "payload": {
            "summary": summary,
            "attachments": attachments or []
        },
        "audit": {
            "createdAt": now,
            "updatedAt": now,
            "immutable": True
        }
    }
    
    if location_description:
        incident_doc["location"]["description"] = location_description
    
    if raw_data:
        incident_doc["payload"]["raw"] = raw_data
    
    logger.info(f"Creating incident: {incident_id} (type={incident_type}, severity={severity}, origin={origin_node_id})")
    incidents.insert_one(incident_doc)
    logger.info(f"Successfully created incident: {incident_id}")
    
    return incident_id


def add_traversal_hop(
    incident_id: str,
    node_id: str,
    node_type: Literal["edge", "relay", "regional", "base"],
    protocol: Literal["http", "mqtt", "radio", "satellite"],
    encrypted: bool = False,
    latency_ms: Optional[float] = None,
    signal_strength: Optional[float] = None,
    geo: Optional[tuple[float, float]] = None,  # (lat, lng)
    checksum: Optional[str] = None,
    verified: bool = True
) -> bool:
    """
    Add a traversal hop to an existing incident's path.
    
    Args:
        incident_id: ID of the incident
        node_id: ID of the node in this hop
        node_type: Type of node ("edge", "relay", "regional", "base")
        protocol: Transport protocol used
        encrypted: Whether the transmission was encrypted
        latency_ms: Optional latency in milliseconds
        signal_strength: Optional signal strength
        geo: Optional tuple of (latitude, longitude)
        checksum: Optional checksum for integrity verification
        verified: Whether the hop has been verified (default: True)
    
    Returns:
        bool: True if successful
    """
    logger.debug(f"Adding traversal hop for incident {incident_id}: node={node_id}, type={node_type}")
    db = get_mongodb_connection()
    incidents: Collection = db["incidents"]
    
    # Get current incident to determine hop index
    incident = incidents.find_one({"incidentId": incident_id})
    if not incident:
        logger.warning(f"Incident {incident_id} not found when adding traversal hop")
        raise ValueError(f"Incident {incident_id} not found")
    
    hop_index = len(incident.get("traversalPath", []))
    now = datetime.utcnow()
    
    hop = {
        "hopIndex": hop_index,
        "nodeId": node_id,
        "nodeType": node_type,
        "receivedAt": now,
        "transport": {
            "protocol": protocol,
            "encrypted": encrypted
        },
        "integrity": {
            "verified": verified
        }
    }
    
    if latency_ms is not None:
        hop["transport"]["latencyMs"] = latency_ms
    
    if signal_strength is not None:
        hop["transport"]["signalStrength"] = signal_strength
    
    if geo:
        hop["geo"] = {
            "lat": geo[0],
            "lng": geo[1]
        }
    
    if checksum:
        hop["integrity"]["checksum"] = checksum
    
    # Update the incident with the new hop
    result = incidents.update_one(
        {"incidentId": incident_id},
        {
            "$push": {"traversalPath": hop},
            "$set": {"audit.updatedAt": now}
        }
    )
    
    if result.modified_count > 0:
        logger.info(f"Added traversal hop {hop_index} for incident {incident_id}: {node_id} ({node_type})")
    else:
        logger.warning(f"Failed to add traversal hop for incident {incident_id}")
    
    return result.modified_count > 0


def update_incident_status(
    incident_id: str,
    status: Literal["open", "in_progress", "resolved", "archived"]
) -> bool:
    """
    Update the status of an incident.
    
    Args:
        incident_id: ID of the incident
        status: New status
    
    Returns:
        bool: True if successful
    """
    logger.info(f"Updating incident {incident_id} status to: {status}")
    db = get_mongodb_connection()
    incidents: Collection = db["incidents"]
    
    result = incidents.update_one(
        {"incidentId": incident_id},
        {
            "$set": {
                "status": status,
                "audit.updatedAt": datetime.utcnow()
            }
        }
    )
    
    if result.modified_count > 0:
        logger.info(f"Successfully updated incident {incident_id} status to: {status}")
    else:
        logger.warning(f"Failed to update status for incident {incident_id} (not found or no change)")
    
    return result.modified_count > 0


def update_base_receipt_status(
    incident_id: str,
    processing_status: Literal["queued", "processing", "completed"]
) -> bool:
    """
    Update the processing status at the base station.
    
    Args:
        incident_id: ID of the incident
        processing_status: New processing status
    
    Returns:
        bool: True if successful
    """
    logger.debug(f"Updating base receipt status for incident {incident_id} to: {processing_status}")
    db = get_mongodb_connection()
    incidents: Collection = db["incidents"]
    
    result = incidents.update_one(
        {"incidentId": incident_id},
        {
            "$set": {
                "baseReceipt.processingStatus": processing_status,
                "audit.updatedAt": datetime.utcnow()
            }
        }
    )
    
    if result.modified_count > 0:
        logger.info(f"Updated base receipt status for incident {incident_id} to: {processing_status}")
    else:
        logger.warning(f"Failed to update base receipt status for incident {incident_id}")
    
    return result.modified_count > 0


def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve an incident by ID.
    
    Args:
        incident_id: ID of the incident
    
    Returns:
        Dict containing the incident data, or None if not found
    """
    logger.debug(f"Retrieving incident: {incident_id}")
    db = get_mongodb_connection()
    incidents: Collection = db["incidents"]
    
    incident = incidents.find_one({"incidentId": incident_id}, {"_id": 0})
    
    if incident:
        logger.debug(f"Found incident: {incident_id}")
    else:
        logger.warning(f"Incident not found: {incident_id}")
    
    return incident


def get_active_incidents() -> List[Dict[str, Any]]:
    """
    Get all active (non-archived) incidents.
    
    Returns:
        List of incident documents
    """
    logger.debug("Retrieving all active incidents")
    db = get_mongodb_connection()
    incidents: Collection = db["incidents"]
    
    result = list(incidents.find(
        {"status": {"$ne": "archived"}},
        {"_id": 0}
    ).sort("audit.createdAt", -1))
    
    logger.info(f"Retrieved {len(result)} active incidents")
    return result
