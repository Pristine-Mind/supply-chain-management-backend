# 🔐 External Business Authentication Guide

The external delivery system supports **dual authentication methods** for different use cases:

## 🚀 **Authentication Methods**

### **1. API Key Authentication (For API Integration)**
- **Use Case**: Server-to-server API calls, webhooks, automated systems
- **Method**: HTTP header `X-API-Key`
- **Stateless**: No session management required
- **Suitable for**: Production integrations, mobile apps, third-party systems

### **2. JWT Token Authentication (For Dashboard Access)**  
- **Use Case**: Web dashboard login, user sessions, frontend applications
- **Method**: Bearer token in Authorization header
- **Stateful**: Managed sessions with refresh tokens
- **Suitable for**: Web interfaces, admin dashboards, user portals

---

## 📋 **Getting Started - Complete Flow**

### **Step 1: Business Registration**
```python
import requests

# Register your business first
response = requests.post('/api/public/external-delivery/register/', {
    'business_name': 'My Ecommerce Store',
    'business_email': 'api@mystore.com',
    'contact_person': 'John Doe', 
    'contact_phone': '+977-9841234567',
    'business_address': '123 Store Street',
    'website': 'https://mystore.com',
    'webhook_url': 'https://mystore.com/webhooks/delivery'
})

# Returns: {"message": "Registration submitted successfully..."}
# Wait for admin approval...
```

### **Step 2: Setup User Account (After Approval)**
```python
# After business approval, you'll receive an API key
# Use it to setup your user account for dashboard access

response = requests.post('/api/public/external-delivery/auth/setup/', {
    'api_key': 'ext_your_received_api_key_here',
    'password': 'SecurePassword123!',
    'confirm_password': 'SecurePassword123!'
})

# Returns: {"message": "Account setup successful. You can now login."}
```

### **Step 3: Choose Your Authentication Method**

#### **Option A: API Key (For Server Integration)**
```python
headers = {'X-API-Key': 'ext_your_api_key_here'}

# Create delivery via API
response = requests.post('/api/external/deliveries/', 
    headers=headers,
    json={
        'external_delivery_id': 'ORDER_123',
        'pickup_name': 'Store Warehouse',
        'pickup_address': '123 Store Street',
        'pickup_city': 'Kathmandu',
        'delivery_name': 'Customer Name',
        'delivery_address': '456 Customer Street', 
        'delivery_city': 'Lalitpur',
        'package_description': 'Electronics',
        'package_weight': 2.5,
        'delivery_fee': 250.00
    }
)
```

#### **Option B: JWT Login (For Dashboard)**
```python
# Login to get JWT tokens
response = requests.post('/api/public/external-delivery/auth/login/', {
    'email': 'api@mystore.com',
    'password': 'SecurePassword123!'
})

tokens = response.json()
# Returns: {
#   "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci...", 
#   "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
#   "business": {...},
#   "expires_in": 3600
# }

# Use access token for dashboard API calls
headers = {'Authorization': f'Bearer {tokens["access_token"]}'}

# Access dashboard data
dashboard = requests.get('/api/external/dashboard/', headers=headers)
```

---

## 🔄 **JWT Token Management**

### **Refresh Tokens**
```python
# When access token expires, refresh it
response = requests.post('/api/public/external-delivery/auth/refresh/', {
    'refresh_token': 'your_refresh_token_here'
})

new_tokens = response.json()
# Returns: {"access_token": "...", "expires_in": 3600}
```

### **Logout**
```python
# Logout and blacklist tokens
headers = {'Authorization': f'Bearer {access_token}'}
requests.post('/api/public/external-delivery/auth/logout/', 
    headers=headers,
    json={'refresh_token': refresh_token}
)
```

---

## 🛠 **Frontend Implementation Examples**

### **React.js Dashboard Integration**
```javascript
// auth.js - Authentication service
class AuthService {
  constructor() {
    this.baseURL = 'https://yourapi.com/api/public/external-delivery';
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
  }

  async login(email, password) {
    try {
      const response = await fetch(`${this.baseURL}/auth/login/`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email, password})
      });

      if (response.ok) {
        const data = await response.json();
        this.setTokens(data.access_token, data.refresh_token);
        return {success: true, business: data.business};
      } else {
        const error = await response.json();
        return {success: false, error: error.error};
      }
    } catch (error) {
      return {success: false, error: 'Network error'};
    }
  }

  setTokens(accessToken, refreshToken) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
  }

  async apiCall(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const headers = {
      'Authorization': `Bearer ${this.accessToken}`,
      'Content-Type': 'application/json',
      ...options.headers
    };

    try {
      let response = await fetch(url, {...options, headers});
      
      // If token expired, try to refresh
      if (response.status === 401) {
        const refreshed = await this.refreshAccessToken();
        if (refreshed) {
          headers['Authorization'] = `Bearer ${this.accessToken}`;
          response = await fetch(url, {...options, headers});
        }
      }

      return response;
    } catch (error) {
      throw new Error('API call failed');
    }
  }

  async refreshAccessToken() {
    try {
      const response = await fetch(`${this.baseURL}/auth/refresh/`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({refresh_token: this.refreshToken})
      });

      if (response.ok) {
        const data = await response.json();
        this.setTokens(data.access_token, this.refreshToken);
        return true;
      } else {
        this.logout();
        return false;
      }
    } catch (error) {
      this.logout();
      return false;
    }
  }

  logout() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  isAuthenticated() {
    return !!this.accessToken;
  }
}

// Usage in React component
import React, {useState} from 'react';

const LoginForm = () => {
  const [credentials, setCredentials] = useState({email: '', password: ''});
  const [loading, setLoading] = useState(false);
  const auth = new AuthService();

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    const result = await auth.login(credentials.email, credentials.password);
    
    if (result.success) {
      // Redirect to dashboard
      window.location.href = '/dashboard';
    } else {
      alert(result.error);
    }
    
    setLoading(false);
  };

  return (
    <form onSubmit={handleLogin}>
      <input 
        type="email" 
        placeholder="Business Email"
        value={credentials.email}
        onChange={(e) => setCredentials({...credentials, email: e.target.value})}
        required 
      />
      <input 
        type="password" 
        placeholder="Password"
        value={credentials.password}
        onChange={(e) => setCredentials({...credentials, password: e.target.value})}
        required 
      />
      <button type="submit" disabled={loading}>
        {loading ? 'Logging in...' : 'Login'}
      </button>
    </form>
  );
};
```

### **Dashboard Component Example**
```javascript
const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [deliveries, setDeliveries] = useState([]);
  const auth = new AuthService();

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const response = await auth.apiCall('/dashboard/');
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    }
  };

  const createDelivery = async (deliveryData) => {
    try {
      const response = await auth.apiCall('/deliveries/', {
        method: 'POST',
        body: JSON.stringify(deliveryData)
      });

      if (response.ok) {
        const delivery = await response.json();
        setDeliveries(prev => [delivery, ...prev]);
        return {success: true, delivery};
      } else {
        const error = await response.json();
        return {success: false, error};
      }
    } catch (error) {
      return {success: false, error: 'Network error'};
    }
  };

  return (
    <div>
      <h1>Delivery Dashboard</h1>
      {stats && (
        <div className="stats">
          <div>Total Deliveries: {stats.total_deliveries}</div>
          <div>This Month: {stats.current_month_deliveries}</div>
          <div>Success Rate: {stats.success_rate}%</div>
        </div>
      )}
      {/* Add delivery creation form, delivery list, etc. */}
    </div>
  );
};
```

---

## 🔒 **Security Features**

### **JWT Security**
- **1 hour access token lifetime** (configurable)
- **7 day refresh token lifetime** (configurable) 
- **Automatic token rotation** on refresh
- **Token blacklisting** on logout
- **Business-specific claims** in tokens

### **API Key Security**
- **Unique 48-character keys** (UUID-based)
- **Business status validation** (must be approved)
- **Rate limiting** per business plan
- **Usage logging** for audit trails

### **Additional Security**
- **CORS protection** for browser requests
- **Request size limits** (1MB max)
- **Webhook HMAC verification** 
- **SSL/TLS enforcement** in production

---

## 📱 **Mobile App Integration**

### **Flutter Example**
```dart
// auth_service.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class AuthService {
  static const String baseUrl = 'https://yourapi.com/api/public/external-delivery';
  String? _accessToken;
  String? _refreshToken;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken = prefs.getString('access_token');
    _refreshToken = prefs.getString('refresh_token');
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/login/'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'email': email, 'password': password}),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        await _saveTokens(data['access_token'], data['refresh_token']);
        return {'success': true, 'business': data['business']};
      } else {
        final error = json.decode(response.body);
        return {'success': false, 'error': error['error']};
      }
    } catch (e) {
      return {'success': false, 'error': 'Network error'};
    }
  }

  Future<void> _saveTokens(String accessToken, String refreshToken) async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    await prefs.setString('access_token', accessToken);
    await prefs.setString('refresh_token', refreshToken);
  }

  Future<http.Response?> apiCall(String endpoint, {String method = 'GET', Map<String, dynamic>? body}) async {
    final url = Uri.parse('$baseUrl$endpoint');
    final headers = {
      'Authorization': 'Bearer $_accessToken',
      'Content-Type': 'application/json',
    };

    http.Response response;
    
    try {
      switch (method.toUpperCase()) {
        case 'POST':
          response = await http.post(url, headers: headers, body: json.encode(body));
          break;
        case 'PUT':
          response = await http.put(url, headers: headers, body: json.encode(body));
          break;
        default:
          response = await http.get(url, headers: headers);
      }

      if (response.statusCode == 401) {
        final refreshed = await _refreshAccessToken();
        if (refreshed) {
          headers['Authorization'] = 'Bearer $_accessToken';
          switch (method.toUpperCase()) {
            case 'POST':
              response = await http.post(url, headers: headers, body: json.encode(body));
              break;
            case 'PUT':
              response = await http.put(url, headers: headers, body: json.encode(body));
              break;
            default:
              response = await http.get(url, headers: headers);
          }
        }
      }

      return response;
    } catch (e) {
      print('API call error: $e');
      return null;
    }
  }

  Future<bool> _refreshAccessToken() async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/refresh/'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'refresh_token': _refreshToken}),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        await _saveTokens(data['access_token'], _refreshToken!);
        return true;
      } else {
        await logout();
        return false;
      }
    } catch (e) {
      await logout();
      return false;
    }
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken = null;
    _refreshToken = null;
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
  }

  bool get isAuthenticated => _accessToken != null;
}
```

---

## 🌟 **Best Practices**

### **For API Key Usage:**
1. **Store securely** on server-side only
2. **Use HTTPS** for all requests
3. **Implement rate limiting** on your side
4. **Monitor API usage** via logs
5. **Rotate keys periodically**

### **For JWT Usage:**
1. **Store tokens securely** (avoid localStorage for sensitive data)
2. **Implement auto-refresh** logic
3. **Handle token expiry** gracefully
4. **Logout on suspicious activity**
5. **Use HTTPS only**

### **General Security:**
1. **Validate all inputs** before API calls
2. **Implement request timeouts**
3. **Log authentication events**
4. **Monitor for abuse patterns**
5. **Keep credentials confidential**

---

## 🆘 **Troubleshooting**

### **Common Issues:**
1. **"Invalid API key"** → Check business approval status
2. **"Token expired"** → Implement refresh logic
3. **"Rate limit exceeded"** → Check usage limits
4. **"Account not setup"** → Complete account setup first
5. **"Invalid credentials"** → Verify email/password

### **Getting Help:**
- Check API response error messages
- Review authentication logs
- Contact support with API key for assistance
- Use test endpoints to validate setup

The dual authentication system provides flexibility for both automated integrations and user-facing dashboards! 🚀