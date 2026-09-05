from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

# 1. Graph Enums


class NodeType(str, Enum):
    STORE = "VStore"
    PRODUCT = "VProduct"
    CATEGORY = "VCategory"


class EdgeType(str, Enum):
    TRANSACTED = "ETransacted"
    OFFERS = "EOffers"
    CATEGORIZED = "ECategorized"
    ACTION = "EAction"


class BusinessRole(str, Enum):
    DISTRIBUTOR = "distributor"
    WHOLESALER = "wholesaler"
    RETAILER = "retailer"
    GENERAL_USER = "general user"


# 2. Graph Injection Models


class GraphNode(BaseModel):
    node_id: int
    node_type: NodeType
    raw_text_feature: str
    business_role: Optional[BusinessRole] = None


class GraphEdge(BaseModel):
    source_id: int
    target_id: int
    source_type: NodeType
    target_type: NodeType
    edge_type: EdgeType
    weight: float = 1.0
