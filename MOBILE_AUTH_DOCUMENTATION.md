# Mobile Authentication & Registration Documentation

This document outlines the API endpoints and flows for mobile-based user registration and authentication using OTP (One-Time Password).

## 1. User Registration

The registration process has been updated to require a phone number, which is essential for the mobile login flow.

### Endpoint
`POST /api/register/user/` or `POST /register/`

### Request Headers
- `Content-Type: application/json`

### Request Body
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Unique username for the account |
| `email` | string | Yes | Valid email address |
| `password` | string | Yes | Password for the account |
| `password2` | string | Yes | Password confirmation (must match `password`) |
| `first_name` | string | Yes | User's first name |
| `last_name` | string | Yes | User's last name |
| `phone_number` | string | **Yes** | **Mobile number for OTP authentication** |
| `location` | integer | No | ID of the City (optional) |

### Example Request
```json
{
    "username": "mobile_user_01",
    "email": "mobile.user@example.com",
    "password": "SecurePassword123!",
    "password2": "SecurePassword123!",
    "first_name": "Rishi",
    "last_name": "Khatri",
    "phone_number": "9800000000"
}
```

### Example Response (201 Created)
```json
{
    "message": "User Created Successfully. Now perform Login to get your token"
}
```

---

## 2. Mobile Login (OTP Flow)

The mobile login is a two-step process:
1.  **Request OTP**: The user submits their phone number.
2.  **Verify OTP**: The user submits the phone number and the received OTP to authenticate.

### Endpoint
`POST /api/phone-login/`

### Step 1: Request OTP

Send the phone number to trigger an OTP. If the user exists, an OTP will be generated.

#### Request Body
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone_number` | string | Yes | The registered mobile number |

#### Example Request
```json
{
    "phone_number": "9800000000"
}
```

#### Example Response (200 OK)
```json
{
    "message": "OTP sent successfully",
    "otp": "123456" 
}
```
*(Note: In a production environment, the `otp` field should be removed from the response and sent via SMS provider)*

### Step 2: Verify OTP & Login

Submit the phone number along with the OTP received to get the authentication token.

#### Request Body
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone_number` | string | Yes | The registered mobile number |
| `otp` | string | Yes | The 6-digit code received |

#### Example Request
```json
{
    "phone_number": "9800000000",
    "otp": "123456"
}
```

#### Example Response (200 OK)
Returns the authentication token and user profile details.

```json
{
    "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
    "has_access_to_marketplace": false,
    "business_type": null,
    "shop_id": null,
    "b2b_verified": false
}
```

---

## 3. Error Handling

### Common Error Responses

#### User Not Found
If the phone number is not registered in the system.
```json
{
    "error": "No user found with this phone number."
}
```
**Status Code:** `404 Not Found`

#### Invalid OTP
If the provided OTP is incorrect or expired.
```json
{
    "error": "Invalid OTP",
    "attempts_remaining": 2
}
```
**Status Code:** `400 Bad Request`

#### Account Locked
If too many failed attempts occur.
```json
{
    "error": "Account temporarily locked due to too many failed login attempts.",
    "retry_after": 850,
    "locked_until": "2025-12-10T10:15:00.000000+00:00"
}
```
**Status Code:** `423 Locked`
