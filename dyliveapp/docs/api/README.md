# DyLiveApp API 文档

## 概述

DyLiveApp API 提供了一套完整的RESTful接口，用于管理用户、标签和话术等资源。所有的API都需要通过身份验证才能访问。

## 认证

API使用JWT（JSON Web Token）进行身份验证。在调用需要认证的API时，需要在HTTP请求头中添加`Authorization`字段，格式为：

```
Authorization: Bearer <access_token>
```

### 获取Token

**请求**：
```http
POST /api/users/login/
Content-Type: application/json

{
    "phone_number": "手机号",
    "password": "密码"
}
```

**响应**：
```json
{
    "tokens": {
        "access": "access_token",
        "refresh": "refresh_token"
    },
    "user": {
        "id": 1,
        "name": "用户名",
        "phone_number": "手机号"
    }
}
```

## 用户管理

### 注册用户

**请求**：
```http
POST /api/users/
Content-Type: application/json

{
    "name": "用户名",
    "phone_number": "手机号",
    "password": "密码",
    "confirm_password": "确认密码"
}
```

**响应**：
```json
{
    "id": 1,
    "name": "用户名",
    "phone_number": "手机号"
}
```

### 更新用户信息

**请求**：
```http
PATCH /api/users/profile/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "name": "新用户名"
}
```

**响应**：
```json
{
    "id": 1,
    "name": "新用户名",
    "phone_number": "手机号"
}
```

### 修改密码

**请求**：
```http
POST /api/users/change-password/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "old_password": "旧密码",
    "new_password": "新密码",
    "confirm_password": "确认新密码"
}
```

**响应**：
```json
{
    "message": "密码修改成功"
}
```

## 标签管理

### 获取标签列表

**请求**：
```http
GET /api/tags/
Authorization: Bearer <access_token>
```

**查询参数**：
- `search`: 按标签名称搜索
- `created_by`: 按创建者ID过滤
- `page`: 页码
- `page_size`: 每页数量

**响应**：
```json
{
    "count": 10,
    "next": "下一页URL",
    "previous": "上一页URL",
    "results": [
        {
            "id": 1,
            "tag_name": "标签名称",
            "description": "标签描述",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    ]
}
```

### 创建标签

**请求**：
```http
POST /api/tags/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "tag_name": "标签名称",
    "description": "标签描述"
}
```

**响应**：
```json
{
    "id": 1,
    "tag_name": "标签名称",
    "description": "标签描述",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

### 更新标签

**请求**：
```http
PATCH /api/tags/{tag_id}/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "tag_name": "新标签名称",
    "description": "新标签描述"
}
```

**响应**：
```json
{
    "id": 1,
    "tag_name": "新标签名称",
    "description": "新标签描述",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

### 删除标签

**请求**：
```http
DELETE /api/tags/{tag_id}/
Authorization: Bearer <access_token>
```

**响应**：
```
204 No Content
```

## 话术管理

### 获取话术列表

**请求**：
```http
GET /api/scripts/
Authorization: Bearer <access_token>
```

**查询参数**：
- `search`: 按标题或内容搜索
- `tags`: 按标签ID过滤，多个标签用逗号分隔
- `script_type`: 按话术类型过滤
- `created_by`: 按创建者ID过滤
- `version`: 按版本号过滤
- `page`: 页码
- `page_size`: 每页数量

**响应**：
```json
{
    "count": 10,
    "next": "下一页URL",
    "previous": "上一页URL",
    "results": [
        {
            "id": 1,
            "title": "话术标题",
            "content": "话术内容",
            "script_type": "custom",
            "tags": [1, 2],
            "version": 1,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    ]
}
```

### 创建话术

**请求**：
```http
POST /api/scripts/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "title": "话术标题",
    "content": "话术内容",
    "script_type": "custom",
    "tags": [1, 2]
}
```

**响应**：
```json
{
    "id": 1,
    "title": "话术标题",
    "content": "话术内容",
    "script_type": "custom",
    "tags": [1, 2],
    "version": 1,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

### 更新话术

**请求**：
```http
PATCH /api/scripts/{script_id}/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "title": "新话术标题",
    "content": "新话术内容",
    "tags": [1, 2, 3]
}
```

**响应**：
```json
{
    "id": 1,
    "title": "新话术标题",
    "content": "新话术内容",
    "script_type": "custom",
    "tags": [1, 2, 3],
    "version": 1,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

### 删除话术

**请求**：
```http
DELETE /api/scripts/{script_id}/
Authorization: Bearer <access_token>
```

**响应**：
```
204 No Content
```

### 创建新版本

**请求**：
```http
POST /api/scripts/{script_id}/new_version/
Authorization: Bearer <access_token>
```

**响应**：
```json
{
    "id": 2,
    "title": "话术标题",
    "content": "话术内容",
    "script_type": "custom",
    "tags": [1, 2],
    "version": 2,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

### 获取话术版本列表

**请求**：
```http
GET /api/scripts/{script_id}/versions/
Authorization: Bearer <access_token>
```

**响应**：
```json
[
    {
        "id": 2,
        "version": 2,
        "title": "话术标题",
        "created_at": "2024-01-01T00:00:00Z"
    },
    {
        "id": 1,
        "version": 1,
        "title": "话术标题",
        "created_at": "2024-01-01T00:00:00Z"
    }
]
```

## 错误处理

API使用标准的HTTP状态码表示请求的结果：

- 200: 请求成功
- 201: 创建成功
- 400: 请求参数错误
- 401: 未认证或认证失败
- 403: 权限不足
- 404: 资源不存在
- 500: 服务器内部错误

错误响应的格式如下：

```json
{
    "detail": "错误信息"
}
```

### 常见错误

1. 认证错误
```json
{
    "detail": "无效的token"
}
```

2. 参数验证错误
```json
{
    "field_name": [
        "错误描述"
    ]
}
```

3. 权限错误
```json
{
    "detail": "您没有执行该操作的权限"
}
```

4. 资源不存在
```json
{
    "detail": "未找到"
}
```

## 最佳实践

1. **认证**
   - 妥善保管access_token和refresh_token
   - access_token过期时使用refresh_token获取新的token
   - 在客户端实现token自动刷新机制

2. **请求优化**
   - 使用适当的页码和每页数量控制数据量
   - 合理使用过滤和搜索参数减少数据传输
   - 缓存不经常变化的数据

3. **错误处理**
   - 实现全局错误处理机制
   - 针对不同类型的错误采取相应的处理措施
   - 在开发环境下记录详细的错误信息

4. **版本控制**
   - 在创建新版本前确保当前版本已经稳定
   - 合理使用版本号管理话术内容
   - 保留重要版本的历史记录

## 常见问题

1. **Q: 如何处理token过期？**
   A: 当access_token过期时，使用refresh_token调用刷新接口获取新的token。

2. **Q: 如何批量操作数据？**
   A: 使用相应的批量接口，如批量创建、批量更新等，避免多次调用单个接口。

3. **Q: 如何优化请求性能？**
   A: 使用合适的过滤条件，避免请求过多数据；合理使用缓存；选择合适的请求方法。

4. **Q: 如何处理并发请求？**
   A: 实现请求队列，避免同时发送过多请求；使用节流和防抖机制。