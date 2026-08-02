use serde::Serialize;
use std::fmt::{Display, Formatter};

#[derive(Debug)]
pub struct AppError(pub String);

impl Display for AppError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for AppError {}

impl Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(value: rusqlite::Error) -> Self {
        Self(format!("数据库错误：{value}"))
    }
}

impl From<std::io::Error> for AppError {
    fn from(value: std::io::Error) -> Self {
        Self(format!("文件系统错误：{value}"))
    }
}

impl From<serde_json::Error> for AppError {
    fn from(value: serde_json::Error) -> Self {
        Self(format!("配置格式错误：{value}"))
    }
}

impl From<image::ImageError> for AppError {
    fn from(value: image::ImageError) -> Self {
        Self(format!("图片处理错误：{value}"))
    }
}

impl From<zip::result::ZipError> for AppError {
    fn from(value: zip::result::ZipError) -> Self {
        Self(format!("归档错误：{value}"))
    }
}

pub type AppResult<T> = Result<T, AppError>;
