from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel

ThemeType = Literal["minimal", "modern", "classic"]
VALID_THEMES = {"minimal", "modern", "classic"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================
# SQLModel Database Tables
# ==========================================

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    stripe_customer_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    spaces: List["Space"] = Relationship(back_populates="user", cascade_delete=True)
    embeds: List["Embed"] = Relationship(back_populates="user", cascade_delete=True)


class Space(SQLModel, table=True):
    __tablename__ = "spaces"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    name: str
    title: str
    subtitle: str
    ask: str
    theme: str = Field(default="minimal")  # minimal, modern, classic
    enable_rating: bool = Field(default=True)
    field_configuration: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    public_slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    user: Optional[User] = Relationship(back_populates="spaces")
    testimonials: List["Testimonial"] = Relationship(back_populates="space", cascade_delete=True)
    embeds: List["Embed"] = Relationship(back_populates="space", cascade_delete=True)


class Testimonial(SQLModel, table=True):
    __tablename__ = "testimonials"
    __test__ = False

    id: Optional[int] = Field(default=None, primary_key=True)
    space_id: int = Field(foreign_key="spaces.id")
    customer_name: str
    customer_email: str
    company_name: Optional[str] = Field(default=None)
    social_links: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    profile_photo_url: Optional[str] = Field(default=None)
    testimonial_text: str
    rating: Optional[int] = Field(default=None)
    sharing_consent: bool = Field(default=True)
    is_favorite: bool = Field(default=False)
    is_wall_of_love: bool = Field(default=False)
    is_hidden: bool = Field(default=False)
    submitted_at: datetime = Field(default_factory=utc_now)

    space: Optional[Space] = Relationship(back_populates="testimonials")


class Embed(SQLModel, table=True):
    __tablename__ = "embeds"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    space_id: int = Field(foreign_key="spaces.id")
    display_style: str = Field(default="masonry")  # masonry | carousel
    theme_mode: str = Field(default="light")  # light | dark
    background_color: str = Field(default="#ffffff")
    animation_enabled: bool = Field(default=True)
    content_filter: str = Field(default="all")  # all | wall_of_love
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    user: Optional[User] = Relationship(back_populates="embeds")
    space: Optional[Space] = Relationship(back_populates="embeds")


# ==========================================
# Pydantic Schemas for Request & Response
# ==========================================

class SpaceCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    title: Optional[str] = None
    subtitle: Optional[str] = ""
    ask: Optional[str] = ""
    theme: ThemeType = "minimal"
    enable_rating: bool = True
    field_configuration: Dict[str, Any] = Field(default_factory=dict)
    public_slug: Optional[str] = None


class SpaceUpdate(SQLModel):
    name: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    ask: Optional[str] = None
    theme: Optional[ThemeType] = None
    enable_rating: Optional[bool] = None
    field_configuration: Optional[Dict[str, Any]] = None
    public_slug: Optional[str] = None


class SpaceRead(SQLModel):
    id: int
    user_id: int
    name: str
    title: str
    subtitle: str
    ask: str
    theme: str
    enable_rating: bool
    field_configuration: Dict[str, Any]
    public_slug: str
    created_at: datetime
    updated_at: datetime


class UserCreate(SQLModel):
    email: str
    password: str


class UserRead(SQLModel):
    id: int
    email: str
    stripe_customer_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TestimonialCreate(SQLModel):
    __test__ = False
    customer_name: str
    customer_email: str
    company_name: Optional[str] = None
    social_links: Optional[Dict[str, Any]] = None
    profile_photo_url: Optional[str] = None
    testimonial_text: str
    rating: Optional[int] = None
    sharing_consent: bool = True


class TestimonialUpdate(SQLModel):
    __test__ = False
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    company_name: Optional[str] = None
    social_links: Optional[Dict[str, Any]] = None
    profile_photo_url: Optional[str] = None
    testimonial_text: Optional[str] = None
    rating: Optional[int] = None
    sharing_consent: Optional[bool] = None
    is_favorite: Optional[bool] = None
    is_wall_of_love: Optional[bool] = None
    is_hidden: Optional[bool] = None


class TestimonialRead(SQLModel):
    __test__ = False
    id: int
    space_id: int
    customer_name: str
    customer_email: str
    company_name: Optional[str] = None
    social_links: Optional[Dict[str, Any]] = None
    profile_photo_url: Optional[str] = None
    testimonial_text: str
    rating: Optional[int] = None
    sharing_consent: bool
    is_favorite: bool
    is_wall_of_love: bool
    is_hidden: bool
    submitted_at: datetime


class EmbedCreate(SQLModel):
    space_id: int
    display_style: Literal["masonry", "carousel"] = "masonry"
    theme_mode: Literal["light", "dark"] = "light"
    background_color: str = "#ffffff"
    animation_enabled: bool = True
    content_filter: Literal["all", "wall_of_love"] = "all"


class EmbedUpdate(SQLModel):
    display_style: Optional[Literal["masonry", "carousel"]] = None
    theme_mode: Optional[Literal["light", "dark"]] = None
    background_color: Optional[str] = None
    animation_enabled: Optional[bool] = None
    content_filter: Optional[Literal["all", "wall_of_love"]] = None


class EmbedRead(SQLModel):
    id: int
    user_id: int
    space_id: int
    display_style: str
    theme_mode: str
    background_color: str
    animation_enabled: bool
    content_filter: str
    created_at: datetime
    updated_at: datetime
