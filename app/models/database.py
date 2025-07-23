# app/models/database.py - Minimal working version with fixed relationships

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    UniqueConstraint,
)
from sqlalchemy.sql.sqltypes import Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

Base = declarative_base()


class ContractType(enum.Enum):
    """Contract type enumeration"""

    MAIN = "MAIN"
    AMENDMENT = "AMENDMENT"
    CHANGE_ORDER = "CHANGE_ORDER"
    PROPOSAL = "PROPOSAL"
    SCHEDULE = "SCHEDULE"
    INSURANCE = "INSURANCE"
    CORRESPONDENCE = "CORRESPONDENCE"
    UNKNOWN = "UNKNOWN"


class StorageLocation(enum.Enum):
    """Storage location enumeration"""

    DIGITAL_OCEAN_SPACES = "DIGITAL_OCEAN_SPACES"
    LOCAL_FILESYSTEM = "LOCAL_FILESYSTEM"
    AWS_S3 = "AWS_S3"


class User(Base):
    """User model - SIMPLIFIED"""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    google_id = Column(String(255), unique=True, nullable=True)
    name = Column(String(255), nullable=False)
    picture_url = Column(String(2000), nullable=True)

    # Billing info
    credits_remaining = Column(Numeric(10, 4), default=0.0)
    total_credits_purchased = Column(Numeric(10, 4), default=0.0)

    # Account status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))

    # Stripe subscription fields
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    has_premium = Column(Boolean, default=False, nullable=False)
    subscription_status = Column(String(50), default="free", nullable=False)
    subscription_start_date = Column(DateTime(timezone=True), nullable=True)
    subscription_end_date = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)

    # SIMPLIFIED: Only essential relationships to avoid circular issues
    jobs = relationship("Job", back_populates="user")


class Job(Base):
    """Job model - SIMPLIFIED"""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Job identification
    job_number = Column(String(100), nullable=False, index=True)
    job_name = Column(String(255), nullable=True)

    # Job metadata
    client_name = Column(String(255), nullable=True)
    project_description = Column(Text, nullable=True)
    contract_value = Column(Numeric(15, 2), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Status and tracking
    status = Column(String(50), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Contract statistics
    total_contracts = Column(Integer, default=0)

    # Storage information
    storage_location = Column(
        SQLEnum(StorageLocation), default=StorageLocation.DIGITAL_OCEAN_SPACES
    )
    spaces_prefix = Column(String(500), nullable=True)

    # SIMPLIFIED: Only essential relationships
    user = relationship("User", back_populates="jobs")
    contracts = relationship("Contract", back_populates="job")

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("user_id", "job_number", name="_user_job_number_uc"),
    )


class Contract(Base):
    """Contract model - SIMPLIFIED"""

    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)

    # File identification
    original_filename = Column(String(255), nullable=False)
    safe_filename = Column(String(255), nullable=False)
    file_extension = Column(String(10), nullable=False)

    # Contract classification
    contract_type = Column(SQLEnum(ContractType), default=ContractType.UNKNOWN)
    is_main_contract = Column(Boolean, default=False, index=True)

    # File metadata
    file_size_bytes = Column(BigInteger, nullable=False)
    file_hash = Column(String(64), nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Storage information
    storage_location = Column(
        SQLEnum(StorageLocation), default=StorageLocation.DIGITAL_OCEAN_SPACES
    )
    file_key = Column(String(1000), nullable=False, unique=True)
    public_url = Column(String(1000), nullable=True)
    storage_metadata = Column(Text, nullable=True)

    # Timestamps
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Analysis status
    text_extracted = Column(Boolean, default=False)
    ai_analyzed = Column(Boolean, default=False)
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)

    # SIMPLIFIED: Basic relationship only
    job = relationship("Job", back_populates="contracts")


class AnalysisSession(Base):
    """Analysis session model - MINIMAL to avoid relationship issues"""

    __tablename__ = "analysis_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Session metadata
    session_type = Column(String(50))
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), default="running")

    # Results summary
    total_contracts = Column(Integer, default=0)
    successful_extractions = Column(Integer, default=0)
    successful_classifications = Column(Integer, default=0)
    main_contract_identified = Column(Boolean, default=False)

    # Performance metrics
    total_time_seconds = Column(Numeric(10, 3))
    estimated_cost = Column(Numeric(10, 4))
    actual_cost = Column(Numeric(10, 4))

    # Error information
    error_message = Column(Text)
    error_details = Column(Text)
    failed_contracts = Column(Text)

    # NO RELATIONSHIPS - This is causing the circular issue


class UsageRecord(Base):
    """Usage tracking model - MINIMAL"""

    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("analysis_sessions.id"), nullable=True
    )
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True)

    # Usage details
    contracts_processed = Column(Integer, default=0)
    anthropic_cost = Column(Numeric(10, 6), nullable=False)
    charged_amount = Column(Numeric(10, 6), nullable=False)
    markup_multiplier = Column(Numeric(5, 2), default=2.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # NO RELATIONSHIPS - Keep it simple for now


# Additional models can be added later without relationships
class TextExtraction(Base):
    """Text extraction model"""

    __tablename__ = "text_extractions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)

    extraction_method = Column(String(50), nullable=False)
    extracted_text = Column(Text)
    text_length = Column(Integer, default=0)
    extraction_success = Column(Boolean, default=False)
    extraction_error = Column(Text)
    extraction_time_seconds = Column(Numeric(10, 3))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    confidence_score = Column(Numeric(5, 2))
    page_count = Column(Integer)
    text_storage_key = Column(String(500), nullable=True)


class DocumentClassification(Base):
    """Document classification model"""

    __tablename__ = "document_classifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)

    classification_method = Column(String(50), default="claude_ai")
    document_type = Column(String(50), default="UNKNOWN")
    importance = Column(String(20), default="MEDIUM")
    status = Column(String(50), default="UNKNOWN")
    confidence = Column(String(20), default="MEDIUM")
    summary = Column(Text)
    recommendation = Column(String(50), default="REVIEW_MANUALLY")

    key_parties = Column(Text)
    dollar_amount = Column(String(100))
    project_info = Column(Text)

    ai_model = Column(String(100))
    ai_tokens_used = Column(Integer)
    classification_time_seconds = Column(Numeric(10, 3))
    classification_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnalysisResult(Base):
    """Analysis result model"""

    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("analysis_sessions.id"), nullable=True
    )

    importance_score = Column(Integer, default=0)
    rank = Column(Integer)
    priority_level = Column(String(50))
    is_main_contract = Column(Boolean, default=False)
    ranking_reason = Column(Text)

    key_dates = Column(Text)
    key_amounts = Column(Text)
    risk_factors = Column(Text)
    compliance_notes = Column(Text)

    analysis_date = Column(DateTime(timezone=True), server_default=func.now())
    analyzer_version = Column(String(50))


class ContractRelationship(Base):
    """Track relationships between contracts"""

    __tablename__ = "contract_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_contract_id = Column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False
    )
    child_contract_id = Column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False
    )
    relationship_type = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """Chat message model for document conversations"""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=True)

    # Message content
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)

    # Metadata
    document_filename = Column(String(255), nullable=True)
    job_number = Column(String(100), nullable=True)
    confidence = Column(String(20), nullable=True)  # 'HIGH', 'MEDIUM', 'LOW'

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
