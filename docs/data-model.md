# Data Model (FastAPI / SQLModel)
- `users`: id (int PK), email (str unique), hashed_password (str), stripe_customer_id (str nullable), created_at, updated_at
- `spaces`: id (int PK), user_id (int FK), name (str), title (str), subtitle (str), ask (str), theme (str: minimal|modern|classic), enable_rating (bool), field_configuration (json), public_slug (str unique), created_at, updated_at
- `testimonials`: id (int PK), space_id (int FK), customer_name (str), customer_email (str), company_name (str nullable), social_links (json nullable), profile_photo_url (str nullable), testimonial_text (str), rating (int nullable), sharing_consent (bool), is_favorite (bool), is_wall_of_love (bool), is_hidden (bool), submitted_at (datetime)
- `embeds`: id (int PK), user_id (int FK), space_id (int FK), display_style (str: masonry|carousel), theme_mode (str: light|dark), background_color (str), animation_enabled (bool), content_filter (str: all|wall_of_love), created_at, updated_at
