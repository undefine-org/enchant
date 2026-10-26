//! Both files are inside the captured workspace root but outside either src tree.
pub fn answer() -> u32 {
    include_str!("../../../support/answer.txt")
        .trim()
        .parse()
        .expect("the captured support answer must be an unsigned integer")
}

pub fn message() -> &'static str {
    include_str!("../../../support/message.txt").trim()
}
