use std::collections::HashMap;
use std::sync::RwLock;
use std::time::{Duration, Instant};

pub struct RateLimiter {
    max_requests: usize,
    window: Duration,
    records: RwLock<HashMap<i64, Vec<Instant>>>,
}

impl RateLimiter {
    pub fn new(max_requests: usize, window_secs: u64) -> Self {
        Self {
            max_requests,
            window: Duration::from_secs(window_secs),
            records: RwLock::new(HashMap::new()),
        }
    }

    pub fn check_and_record(&self, user_id: i64) -> bool {
        let now = Instant::now();
        let cutoff = now.checked_sub(self.window).unwrap_or(now);

        let mut map = match self.records.write() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };

        let timestamps = map.entry(user_id).or_default();
        timestamps.retain(|&t| t > cutoff);

        if timestamps.len() >= self.max_requests {
            false
        } else {
            timestamps.push(now);
            true
        }
    }

    #[allow(dead_code)]
    pub fn cleanup(&self) {
        let now = Instant::now();
        let cutoff = now.checked_sub(self.window).unwrap_or(now);

        let mut map = match self.records.write() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };

        map.retain(|_, timestamps| {
            timestamps.retain(|&t| t > cutoff);
            !timestamps.is_empty()
        });
    }
}
