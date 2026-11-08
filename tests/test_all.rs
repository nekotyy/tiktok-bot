use tempfile::tempdir;
use tiktok_bot::db::models::TopUser;
use tiktok_bot::db::Database;
use tiktok_bot::services::rate_limiter::RateLimiter;
use tiktok_bot::services::url_parser::{Platform, URLParser};
use tiktok_bot::utils::formatters::{
    format_duration, format_file_size, format_time_ago, format_top_message, pluralize,
};

#[test]
fn test_url_parser_platforms() {
    // Instagram Reel
    let parsed = URLParser::extract_and_validate(
        "watch this https://www.instagram.com/reel/ABC123/?igsh=test",
    )
    .expect("Failed to parse Instagram reel");
    assert_eq!(parsed.platform, Platform::InstagramReels);
    assert_eq!(parsed.normalized_url, "https://www.instagram.com/reel/ABC123/");

    // Instagram Share Reel
    let parsed = URLParser::extract_and_validate(
        "https://www.instagram.com/share/reel/BA123456789/",
    )
    .expect("Failed to parse Instagram share reel");
    assert_eq!(parsed.platform, Platform::InstagramReels);

    // Instagram Photo Post
    let parsed = URLParser::extract_and_validate(
        "https://www.instagram.com/p/ABC123/",
    )
    .expect("Failed to parse Instagram photo post");
    assert_eq!(parsed.platform, Platform::InstagramReels);

    // Reject Instagram Profile
    let parsed = URLParser::extract_and_validate("https://www.instagram.com/example_user/");
    assert!(parsed.is_none());

    // TikTok
    let parsed = URLParser::extract_and_validate(
        "Check out https://www.tiktok.com/@user/video/7123456789012345678",
    )
    .expect("Failed to parse TikTok video");
    assert_eq!(parsed.platform, Platform::TikTok);

    let parsed = URLParser::extract_and_validate("https://vm.tiktok.com/ZM8abc123/")
        .expect("Failed to parse TikTok short URL");
    assert_eq!(parsed.platform, Platform::TikTok);

    // YouTube Shorts & Video
    let parsed = URLParser::extract_and_validate(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=twitter",
    )
    .expect("Failed to parse YouTube watch");
    assert_eq!(parsed.platform, Platform::YouTubeShorts);
    assert_eq!(
        parsed.normalized_url,
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    );

    let parsed = URLParser::extract_and_validate(
        "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share",
    )
    .expect("Failed to parse YouTube shorts");
    assert_eq!(parsed.platform, Platform::YouTubeShorts);
    assert_eq!(
        parsed.normalized_url,
        "https://www.youtube.com/shorts/dQw4w9WgXcQ"
    );

    let parsed = URLParser::extract_and_validate("https://youtu.be/dQw4w9WgXcQ")
        .expect("Failed to parse youtu.be");
    assert_eq!(parsed.platform, Platform::YouTubeShorts);

    // VK
    let parsed = URLParser::extract_and_validate("https://vk.com/video-123456_789012?list=test")
        .expect("Failed to parse VK video");
    assert_eq!(parsed.platform, Platform::Vk);

    // Other (Twitter / X)
    let parsed = URLParser::extract_and_validate(
        "https://x.com/example/status/1234567890?s=20",
    )
    .expect("Failed to parse X.com");
    assert_eq!(parsed.platform, Platform::Other);

    // Pure Link checking
    assert!(URLParser::is_pure_link_message("  https://vm.tiktok.com/ZM8abc123/ \n"));
    assert!(!URLParser::is_pure_link_message("look at this https://vm.tiktok.com/ZM8abc123/"));
}

#[test]
fn test_formatters() {
    assert_eq!(format_file_size(500), "500 Б");
    assert_eq!(format_file_size(1500), "1.5 КБ");
    assert_eq!(format_file_size(15 * 1024 * 1024), "15.0 МБ");
    assert_eq!(format_file_size(2 * 1024 * 1024 * 1024), "2.0 ГБ");

    assert_eq!(format_duration(Some(90)), "1:30");
    assert_eq!(format_duration(Some(5)), "0:05");
    assert_eq!(format_duration(None), "?");

    assert_eq!(pluralize(1, "день", "дня", "дней"), "день");
    assert_eq!(pluralize(2, "день", "дня", "дней"), "дня");
    assert_eq!(pluralize(5, "день", "дня", "дней"), "дней");
    assert_eq!(pluralize(11, "день", "дня", "дней"), "дней");
    assert_eq!(pluralize(21, "день", "дня", "дней"), "день");

    assert_eq!(format_time_ago(None), "никогда");

    let top_users = vec![
        TopUser {
            user_id: 1,
            total_downloads: 42,
            total_size: 1024 * 1024 * 500,
            last_download_at: None,
            username: Some("alex".to_string()),
            first_name: None,
            last_name: None,
        },
        TopUser {
            user_id: 2,
            total_downloads: 10,
            total_size: 1024 * 1024 * 100,
            last_download_at: None,
            username: None,
            first_name: Some("Ivan".to_string()),
            last_name: Some("Petrov".to_string()),
        },
    ];
    let top_str = format_top_message(&top_users);
    assert!(top_str.contains("1. @alex - 42 скачивания"));
    assert!(top_str.contains("2. Ivan Petrov - 10 скачиваний"));
}

#[test]
fn test_rate_limiter() {
    let limiter = RateLimiter::new(3, 60);
    assert!(limiter.check_and_record(100));
    assert!(limiter.check_and_record(100));
    assert!(limiter.check_and_record(100));
    // 4th request in the same window should be rejected
    assert!(!limiter.check_and_record(100));

    // Another user should still be allowed
    assert!(limiter.check_and_record(200));
}

#[tokio::test]
async fn test_database_operations() {
    let dir = tempdir().expect("Failed to create tempdir");
    let db_path = dir.path().join("test_bot.db");

    let db = Database::new(&db_path).expect("Failed to initialize database");

    // Add user
    let user_added = db
        .add_user(
            12345,
            Some("testuser".to_string()),
            Some("Test".to_string()),
            Some("User".to_string()),
        )
        .await;
    assert!(user_added);

    // Initial stats for user
    let initial_stats = db.get_user_stats(12345).await.expect("Stats should exist");
    assert_eq!(initial_stats.total_downloads, 0);

    // Log successful download
    let logged = db
        .log_download(
            12345,
            "https://vm.tiktok.com/123/".to_string(),
            true,
            Some(10 * 1024 * 1024),
            Some(30),
            None,
        )
        .await;
    assert!(logged);

    // Check updated stats
    let updated_stats = db.get_user_stats(12345).await.expect("Stats should exist");
    assert_eq!(updated_stats.total_downloads, 1);
    assert_eq!(updated_stats.total_size, 10 * 1024 * 1024);

    // Chat settings default
    let default_settings = db.get_chat_settings(9999).await;
    assert!(!default_settings.require_pure_link);
    assert!(default_settings.delete_source_messages);

    // Update chat settings
    let updated = db
        .set_chat_setting(9999, Some(true), Some(false))
        .await;
    assert!(updated);

    let new_settings = db.get_chat_settings(9999).await;
    assert!(new_settings.require_pure_link);
    assert!(!new_settings.delete_source_messages);

    // Global stats
    let global_stats = db.get_global_stats().await.expect("Global stats should exist");
    assert_eq!(global_stats.total_users, 1);
    assert_eq!(global_stats.total_downloads, 1);

    // Top users
    let top = db.get_top_users(5).await;
    assert_eq!(top.len(), 1);
    assert_eq!(top[0].user_id, 12345);
    assert_eq!(top[0].total_downloads, 1);
}
