import React, { useState } from 'react';

// UCI Colors
const colors = {
  uciBlue: '#0064A4',
  uciGold: '#FFD200',
  uciDarkBlue: '#1B3D6D',
  lightGray: '#F5F7FA',
  white: '#FFFFFF',
  success: '#22C55E',
  warning: '#F59E0B',
  error: '#EF4444',
};

export default function WildlifePipelineUI() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'upload', label: 'Upload', icon: '📤' },
    { id: 'model', label: 'Run Model', icon: '🔬' },
    { id: 'review', label: 'Review & Modify', icon: '✏️' },
    { id: 'validate', label: 'Validate', icon: '✅' },
    { id: 'export', label: 'Export', icon: '📥' },
  ];

  const handleLogin = (username) => {
    setCurrentUser({ name: username, role: 'Admin' });
    setIsLoggedIn(true);
  };

  const handleLogout = () => {
    setCurrentUser(null);
    setIsLoggedIn(false);
  };

  if (!isLoggedIn) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar Navigation - Fixed logo display when collapsed */}
      <div 
        className={`${sidebarCollapsed ? 'w-20' : 'w-64'} transition-all duration-300 flex flex-col flex-shrink-0`}
        style={{ backgroundColor: colors.uciDarkBlue }}
      >
        {/* Logo Area - Fixed to always show properly */}
        <div className="p-4 border-b border-blue-800">
          <div className={`flex items-center ${sidebarCollapsed ? 'justify-center' : 'gap-3'}`}>
            <div 
              className="w-12 h-12 rounded-full flex items-center justify-center text-2xl flex-shrink-0"
              style={{ backgroundColor: colors.uciGold }}
            >
              🦌
            </div>
            {!sidebarCollapsed && (
              <div className="text-white overflow-hidden">
                <div className="font-bold text-sm">UCI Nature</div>
                <div className="text-xs text-blue-200">Wildlife Pipeline</div>
              </div>
            )}
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 py-4">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                sidebarCollapsed ? 'justify-center' : ''
              } ${
                activeTab === item.id
                  ? 'text-white border-l-4'
                  : 'text-blue-200 hover:bg-blue-800 hover:text-white border-l-4 border-transparent'
              }`}
              style={activeTab === item.id ? { 
                backgroundColor: 'rgba(255,255,255,0.1)', 
                borderLeftColor: colors.uciGold 
              } : {}}
              title={sidebarCollapsed ? item.label : ''}
            >
              <span className="text-xl flex-shrink-0">{item.icon}</span>
              {!sidebarCollapsed && <span className="text-sm">{item.label}</span>}
            </button>
          ))}
        </nav>

        {/* Collapse Button */}
        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="p-4 text-blue-200 hover:text-white border-t border-blue-800 flex items-center justify-center"
        >
          {sidebarCollapsed ? '→' : '← Collapse'}
        </button>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Header - Added logout button */}
        <header className="bg-white shadow-sm px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold" style={{ color: colors.uciDarkBlue }}>
              {navItems.find(n => n.id === activeTab)?.label}
            </h1>
            <p className="text-sm text-gray-500">UCI Campus Reserves - Wildlife Camera Processing</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right text-sm">
              <div className="text-gray-600">Connected to</div>
              <div className="font-medium text-green-600">Google Drive ✓</div>
            </div>
            <div className="border-l pl-4 flex items-center gap-3">
              <div className="text-right">
                <div className="font-medium text-gray-800">{currentUser?.name}</div>
                <div className="text-xs text-gray-500">{currentUser?.role}</div>
              </div>
              <div 
                className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold"
                style={{ backgroundColor: colors.uciBlue }}
              >
                {currentUser?.name?.charAt(0).toUpperCase()}
              </div>
              {/* Logout Button - Added */}
              <button
                onClick={handleLogout}
                className="ml-2 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                title="Logout"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </button>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6">
          {activeTab === 'dashboard' && <DashboardPage />}
          {activeTab === 'upload' && <UploadPage />}
          {activeTab === 'model' && <ModelPage />}
          {activeTab === 'review' && <ReviewPage />}
          {activeTab === 'validate' && <ValidatePage />}
          {activeTab === 'export' && <ExportPage />}
        </main>
      </div>
    </div>
  );
}

// Login Page
function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (username && password) {
      onLogin(username);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left Side - Nature Image Background */}
      <div 
        className="hidden lg:flex lg:w-1/2 relative"
        style={{ backgroundColor: colors.uciDarkBlue }}
      >
        <div className="absolute inset-0 opacity-20">
          <div className="absolute inset-0" style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
          }}></div>
        </div>
        
        <div className="relative z-10 flex flex-col justify-center items-center w-full p-12 text-white">
          <div 
            className="w-24 h-24 rounded-full flex items-center justify-center text-5xl mb-6"
            style={{ backgroundColor: colors.uciGold }}
          >
            🦌
          </div>
          <h1 className="text-4xl font-bold mb-2">UCI Nature</h1>
          <h2 className="text-xl text-blue-200 mb-8">Wildlife Camera Pipeline</h2>
          
          <div className="space-y-4 text-blue-100">
            <div className="flex items-center gap-3">
              <span className="text-2xl">📷</span>
              <span>Process 100,000+ wildlife images</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-2xl">🤖</span>
              <span>AI-powered animal detection</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-2xl">📊</span>
              <span>Automated data validation</span>
            </div>
          </div>
          
          <div className="absolute bottom-8 text-sm text-blue-200">
            UCI Campus Reserves • School of Biological Sciences
          </div>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 bg-gray-50">
        <div className="w-full max-w-md">
          <div className="lg:hidden text-center mb-8">
            <div 
              className="w-16 h-16 rounded-full flex items-center justify-center text-3xl mx-auto mb-3"
              style={{ backgroundColor: colors.uciGold }}
            >
              🦌
            </div>
            <h1 className="text-2xl font-bold" style={{ color: colors.uciDarkBlue }}>UCI Nature</h1>
          </div>

          <div className="bg-white rounded-2xl shadow-lg p-8">
            <h2 className="text-2xl font-bold mb-2" style={{ color: colors.uciDarkBlue }}>Welcome Back</h2>
            <p className="text-gray-500 mb-6">Sign in to access the Wildlife Pipeline</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  placeholder="Enter your username"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  placeholder="Enter your password"
                />
              </div>

              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="w-4 h-4 rounded"
                  />
                  <span className="text-sm text-gray-600">Remember me</span>
                </label>
                <a href="#" className="text-sm hover:underline" style={{ color: colors.uciBlue }}>
                  Forgot password?
                </a>
              </div>

              <button
                type="submit"
                className="w-full py-3 rounded-lg text-white font-medium transition hover:opacity-90"
                style={{ backgroundColor: colors.uciBlue }}
              >
                Sign In
              </button>
            </form>

            <div className="flex items-center gap-4 my-6">
              <div className="flex-1 border-t border-gray-200"></div>
              <span className="text-sm text-gray-400">or</span>
              <div className="flex-1 border-t border-gray-200"></div>
            </div>

            <button
              onClick={() => onLogin('Julie Coffey')}
              className="w-full py-3 rounded-lg border-2 font-medium transition hover:bg-gray-50 flex items-center justify-center gap-2"
              style={{ borderColor: colors.uciGold, color: colors.uciDarkBlue }}
            >
              <span>🔐</span>
              Sign in with UCI NetID
            </button>
          </div>

          <p className="text-center text-sm text-gray-500 mt-6">
            Need an account? Contact your administrator
          </p>
        </div>
      </div>
    </div>
  );
}

// Dashboard Page - Updated with larger Species Distribution
function DashboardPage() {
  const stats = [
    { label: 'Total Images', value: '102,847', icon: '🖼️', color: 'bg-blue-500' },
    { label: 'Processed', value: '45,231', icon: '✅', color: 'bg-green-500' },
    { label: 'Animals Detected', value: '12,847', icon: '🦊', color: 'bg-amber-500' },
    { label: 'Pending Review', value: '892', icon: '⏳', color: 'bg-purple-500' },
    { label: 'Warnings', value: '156', icon: '⚠️', color: 'bg-red-500' },
  ];

  const speciesData = [
    { name: 'Coyote', percent: 45, color: '#F59E0B', count: 5781 },
    { name: 'Rabbit', percent: 30, color: '#3B82F6', count: 3854 },
    { name: 'Deer', percent: 15, color: '#10B981', count: 1927 },
    { name: 'Bird', percent: 7, color: '#8B5CF6', count: 899 },
    { name: 'Other', percent: 3, color: '#6B7280', count: 386 },
  ];

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-5 gap-4">
        {stats.map((stat, i) => (
          <div key={i} className="bg-white rounded-xl shadow-sm p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-500 text-xs">{stat.label}</p>
                <p className="text-xl font-bold mt-1">{stat.value}</p>
              </div>
              <div className={`${stat.color} w-10 h-10 rounded-lg flex items-center justify-center text-xl text-white`}>
                {stat.icon}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Processing Progress - Full Width */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <h3 className="font-semibold mb-4">Processing Progress</h3>
        <div className="flex items-center gap-4">
          <ProgressStep label="Index" percent={100} color="#3B82F6" />
          <ProgressArrow />
          <ProgressStep label="Download" percent={78} color="#10B981" />
          <ProgressArrow />
          <ProgressStep label="Classify" percent={44} color="#F59E0B" />
          <ProgressArrow />
          <ProgressStep label="Validate" percent={32} color="#8B5CF6" />
          <ProgressArrow />
          <ProgressStep label="Export" percent={0} color="#6B7280" />
        </div>
      </div>

      {/* Two Dashboard Panels - Species Distribution enlarged */}
      <div className="grid grid-cols-2 gap-6">
        {/* Run Summary */}
        <div className="bg-white rounded-xl shadow-sm p-5">
          <h3 className="font-semibold mb-4">Run Summary</h3>
          <div className="flex items-center gap-6">
            {/* Circular Gauge */}
            <div className="relative flex-shrink-0">
              <svg className="w-36 h-36 transform -rotate-90">
                <circle cx="72" cy="72" r="60" stroke="#E5E7EB" strokeWidth="14" fill="none" />
                <circle
                  cx="72" cy="72" r="60"
                  stroke="#22C55E"
                  strokeWidth="14"
                  fill="none"
                  strokeDasharray={`${2 * Math.PI * 60 * 0.95} ${2 * Math.PI * 60}`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold text-green-600">95%</span>
                <span className="text-xs text-gray-500">Success</span>
              </div>
            </div>
            
            {/* Details */}
            <div className="flex-1 space-y-2 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Last Run Status</span>
                <span className="text-green-600 font-medium">✓ Success</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Start Time</span>
                <span>Feb 10, 14:30</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Duration</span>
                <span>25:47</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Images Processed</span>
                <span>5,000</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Failures</span>
                <span className="text-red-500">12</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Throughput</span>
                <span>3.2 img/s</span>
              </div>
            </div>
          </div>
        </div>

        {/* Species Distribution - Enlarged */}
        <div className="bg-white rounded-xl shadow-sm p-5">
          <h3 className="font-semibold mb-4">Species Distribution</h3>
          <div className="flex items-center gap-8">
            {/* Donut Chart - Larger */}
            <div className="relative flex-shrink-0">
              <svg className="w-44 h-44" viewBox="0 0 176 176">
                {speciesData.reduce((acc, species, i) => {
                  const prevPercent = speciesData.slice(0, i).reduce((sum, s) => sum + s.percent, 0);
                  const startAngle = (prevPercent / 100) * 360 - 90;
                  const endAngle = ((prevPercent + species.percent) / 100) * 360 - 90;
                  
                  const startRad = (startAngle * Math.PI) / 180;
                  const endRad = (endAngle * Math.PI) / 180;
                  
                  const x1 = 88 + 70 * Math.cos(startRad);
                  const y1 = 88 + 70 * Math.sin(startRad);
                  const x2 = 88 + 70 * Math.cos(endRad);
                  const y2 = 88 + 70 * Math.sin(endRad);
                  
                  const largeArc = species.percent > 50 ? 1 : 0;
                  
                  acc.push(
                    <path
                      key={i}
                      d={`M 88 88 L ${x1} ${y1} A 70 70 0 ${largeArc} 1 ${x2} ${y2} Z`}
                      fill={species.color}
                    />
                  );
                  return acc;
                }, [])}
                <circle cx="88" cy="88" r="40" fill="white" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold">12,847</span>
                <span className="text-xs text-gray-500">Total</span>
              </div>
            </div>
            
            {/* Legend - With counts */}
            <div className="flex-1 space-y-3">
              {speciesData.map((species, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div 
                    className="w-4 h-4 rounded-full flex-shrink-0"
                    style={{ backgroundColor: species.color }}
                  ></div>
                  <span className="text-sm flex-1">{species.name}</span>
                  <span className="text-sm text-gray-500">{species.count.toLocaleString()}</span>
                  <span className="text-sm font-medium w-12 text-right">{species.percent}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <h3 className="font-semibold mb-4">Recent Activity</h3>
        <div className="space-y-3">
          <ActivityItem time="2 min ago" action="Model completed" detail="Batch #47 - 500 images processed" status="success" />
          <ActivityItem time="15 min ago" action="Upload completed" detail="Research Park camera - 1,200 images" status="success" />
          <ActivityItem time="1 hour ago" action="Validation issue" detail="23 images missing metadata" status="warning" />
          <ActivityItem time="2 hours ago" action="Export completed" detail="Monthly report - 15,000 records" status="success" />
        </div>
      </div>
    </div>
  );
}

// Progress Step Component
function ProgressStep({ label, percent, color }) {
  return (
    <div className="flex-1">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium">{label}</span>
        <span className="text-gray-500">{percent}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-3">
        <div 
          className="h-3 rounded-full transition-all"
          style={{ width: `${percent}%`, backgroundColor: color }}
        ></div>
      </div>
    </div>
  );
}

function ProgressArrow() {
  return <div className="text-gray-300 text-xl mt-4">→</div>;
}

// Upload Page
function UploadPage() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-center">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4 text-3xl">☁️</div>
            <h3 className="font-semibold text-lg mb-2">Sync from Google Drive</h3>
            <p className="text-gray-500 text-sm mb-4">Connect to your shared Drive folder</p>
            <button className="text-white px-6 py-2 rounded-lg transition hover:opacity-90" style={{ backgroundColor: colors.uciBlue }}>
              Connect Drive
            </button>
          </div>
          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <div className="text-sm text-gray-600">Current folder:</div>
            <div className="font-medium">UCI Nature/Wildlife Cameras</div>
            <div className="text-sm text-green-600 mt-1">✓ 102,847 images available</div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-center">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4 text-3xl">📁</div>
            <h3 className="font-semibold text-lg mb-2">Upload Files</h3>
            <p className="text-gray-500 text-sm mb-4">Drag & drop or browse files</p>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 hover:border-blue-400 transition cursor-pointer">
              <p className="text-gray-400">Drop images here</p>
              <p className="text-sm text-gray-400 mt-1">or click to browse</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Camera Locations</h3>
        <div className="grid grid-cols-3 gap-4">
          {['Research Park', 'San Joaquin Marsh', 'Ecological Reserve', 'Burns Piñon Ridge', 'Steele Burnand', 'Crystal Cove'].map((loc, i) => (
            <div key={i} className="border rounded-lg p-4 hover:border-blue-400 cursor-pointer transition">
              <div className="flex items-center gap-3">
                <span className="text-2xl">📷</span>
                <div>
                  <div className="font-medium">{loc}</div>
                  <div className="text-sm text-gray-500">{Math.floor(Math.random() * 20000 + 5000)} images</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Help Icon Component
function HelpIcon({ tooltip }) {
  return (
    <span 
      className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 text-blue-600 text-xs cursor-help ml-2"
      title={tooltip}
    >
      ?
    </span>
  );
}

// Warning Icon Component
function WarningIcon({ tooltip }) {
  return (
    <span 
      className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-yellow-100 text-yellow-600 text-xs cursor-help ml-2"
      title={tooltip}
    >
      !
    </span>
  );
}

// Run Model Page - Updated with help icons
function ModelPage() {
  const [isRunning, setIsRunning] = useState(false);
  const [threshold, setThreshold] = useState(50);
  
  return (
    <div className="space-y-6">
      {/* Model Control */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="font-semibold text-lg">MegaDetector v5</h3>
            <p className="text-gray-500 text-sm">Animal detection and classification</p>
          </div>
          <button 
            onClick={() => setIsRunning(!isRunning)}
            className={`px-8 py-3 rounded-lg font-medium transition ${
              isRunning 
                ? 'bg-red-500 text-white hover:bg-red-600' 
                : 'bg-green-500 text-white hover:bg-green-600'
            }`}
          >
            {isRunning ? '⏹ Stop' : '▶ Run Model'}
          </button>
        </div>

        {isRunning && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span>Processing: batch_047.jpg</span>
              <span>2,451 / 5,000 images</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div className="bg-blue-500 h-3 rounded-full transition-all" style={{width: '49%'}}></div>
            </div>
            <div className="flex justify-between text-sm text-gray-500">
              <span>Elapsed: 12:34</span>
              <span>ETA: 13:22</span>
            </div>
          </div>
        )}
      </div>

      {/* Settings - Updated with help icons */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Settings</h3>
        <div className="grid grid-cols-2 gap-6">
          {/* Confidence Threshold */}
          <div>
            <label className="flex items-center text-sm font-medium mb-2">
              Confidence Threshold
              <HelpIcon tooltip="Images with detection confidence below this threshold will be marked as 'Blank'. Higher threshold = fewer false positives but may miss some animals." />
            </label>
            <input 
              type="range" 
              min="0" 
              max="100" 
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              className="w-full" 
            />
            <div className="flex justify-between text-sm text-gray-500 mt-1">
              <span>0%</span>
              <span className="font-medium text-blue-600">{threshold}%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Batch Size */}
          <div>
            <label className="flex items-center text-sm font-medium mb-2">
              Batch Size
              <WarningIcon tooltip="Larger batches are more efficient but use more memory. 'All images' processes everything in one run." />
            </label>
            <select className="w-full border rounded-lg p-2">
              <option>100 images</option>
              <option>500 images</option>
              <option>1000 images</option>
              <option>All images</option>
            </select>
          </div>
        </div>
      </div>

      {/* Recent Runs */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Recent Runs</h3>
        <table className="w-full">
          <thead className="text-left text-sm text-gray-500 border-b">
            <tr>
              <th className="pb-2">Date</th>
              <th className="pb-2">Images</th>
              <th className="pb-2">Animals</th>
              <th className="pb-2">Blank</th>
              <th className="pb-2">Duration</th>
              <th className="pb-2">Status</th>
            </tr>
          </thead>
          <tbody className="text-sm">
            <tr className="border-b">
              <td className="py-3">Feb 10, 2026</td>
              <td>5,000</td>
              <td>1,247</td>
              <td>3,753</td>
              <td>25:47</td>
              <td><span className="text-green-600">✓ Complete</span></td>
            </tr>
            <tr className="border-b">
              <td className="py-3">Feb 9, 2026</td>
              <td>3,500</td>
              <td>892</td>
              <td>2,608</td>
              <td>18:22</td>
              <td><span className="text-green-600">✓ Complete</span></td>
            </tr>
            <tr className="border-b">
              <td className="py-3">Feb 8, 2026</td>
              <td>2,000</td>
              <td>456</td>
              <td>1,532</td>
              <td>10:15</td>
              <td><span className="text-yellow-600">⚠ Partial</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Review Page
function ReviewPage() {
  const [selectedImage, setSelectedImage] = useState(0);
  
  const images = [
    { id: 1, name: 'IMG_0421.jpg', classification: 'Coyote', confidence: 94, status: 'confirmed' },
    { id: 2, name: 'IMG_0422.jpg', classification: 'Blank', confidence: 99, status: 'confirmed' },
    { id: 3, name: 'IMG_0423.jpg', classification: 'Unknown', confidence: 45, status: 'needs_review' },
    { id: 4, name: 'IMG_0424.jpg', classification: 'Rabbit', confidence: 87, status: 'confirmed' },
    { id: 5, name: 'IMG_0425.jpg', classification: 'Deer', confidence: 62, status: 'needs_review' },
  ];

  return (
    <div className="flex gap-6 h-full">
      <div className="w-80 bg-white rounded-xl shadow-sm p-4 overflow-auto">
        <div className="mb-4">
          <input type="text" placeholder="Search images..." className="w-full border rounded-lg p-2 text-sm" />
        </div>
        <div className="flex gap-2 mb-4">
          <button className="px-3 py-1 bg-orange-100 text-orange-700 rounded-full text-xs">Needs Review (23)</button>
          <button className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-xs">All</button>
        </div>
        <div className="space-y-2">
          {images.map((img, i) => (
            <div 
              key={img.id}
              onClick={() => setSelectedImage(i)}
              className={`p-3 rounded-lg cursor-pointer transition ${
                selectedImage === i ? 'bg-blue-50 border-2 border-blue-400' : 'hover:bg-gray-50 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gray-200 rounded flex items-center justify-center">🖼️</div>
                <div className="flex-1">
                  <div className="font-medium text-sm">{img.name}</div>
                  <div className="text-xs text-gray-500">{img.classification} ({img.confidence}%)</div>
                </div>
                {img.status === 'needs_review' && (
                  <span className="w-2 h-2 bg-orange-400 rounded-full"></span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 bg-white rounded-xl shadow-sm p-6">
        <div className="aspect-video bg-gray-800 rounded-lg mb-4 flex items-center justify-center">
          <span className="text-6xl">🦊</span>
        </div>
        
        <div className="grid grid-cols-2 gap-6">
          <div>
            <h4 className="font-semibold mb-3">Classification</h4>
            <div className="space-y-2">
              <label className="block">
                <span className="text-sm text-gray-600">Species</span>
                <select className="w-full border rounded-lg p-2 mt-1">
                  <option>Coyote</option>
                  <option>Rabbit</option>
                  <option>Deer</option>
                  <option>Bird</option>
                  <option>Blank</option>
                  <option>Other</option>
                </select>
              </label>
              <label className="block">
                <span className="text-sm text-gray-600">Count</span>
                <input type="number" defaultValue="1" className="w-full border rounded-lg p-2 mt-1" />
              </label>
            </div>
          </div>
          
          <div>
            <h4 className="font-semibold mb-3">Metadata</h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">Camera:</span><span>Research Park #3</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Date:</span><span>2024-05-13</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Time:</span><span>14:32:07</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Confidence:</span><span>94%</span></div>
            </div>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button className="flex-1 bg-green-500 text-white py-2 rounded-lg hover:bg-green-600">✓ Confirm</button>
          <button className="flex-1 bg-gray-200 text-gray-700 py-2 rounded-lg hover:bg-gray-300">Skip</button>
          <button className="flex-1 bg-red-100 text-red-700 py-2 rounded-lg hover:bg-red-200">Flag Issue</button>
        </div>
      </div>
    </div>
  );
}

// Validate Page
function ValidatePage() {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="font-semibold text-lg">Data Validation</h3>
          <button className="text-white px-4 py-2 rounded-lg hover:opacity-90" style={{ backgroundColor: colors.uciBlue }}>
            Run Validation
          </button>
        </div>
        
        <div className="grid grid-cols-4 gap-4">
          <ValidationCard title="Total Records" value="45,231" status="info" />
          <ValidationCard title="Valid" value="44,892" status="success" />
          <ValidationCard title="Warnings" value="287" status="warning" />
          <ValidationCard title="Errors" value="52" status="error" />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Validation Checks</h3>
        <div className="space-y-3">
          <CheckItem label="All required columns present" status="pass" detail="9/9 columns" />
          <CheckItem label="Image IDs are unique" status="pass" detail="45,231 unique IDs" />
          <CheckItem label="Date/Time populated" status="warning" detail="287 missing values" />
          <CheckItem label="Camera names valid" status="pass" detail="All match known cameras" />
          <CheckItem label="ML classification complete" status="error" detail="52 images not processed" />
          <CheckItem label="Confidence scores in range" status="pass" detail="All values 0-1" />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Issues to Resolve</h3>
        <table className="w-full text-sm">
          <thead className="text-left text-gray-500 border-b">
            <tr>
              <th className="pb-2">Type</th>
              <th className="pb-2">Field</th>
              <th className="pb-2">Count</th>
              <th className="pb-2">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b">
              <td className="py-3"><span className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs">Warning</span></td>
              <td>date</td>
              <td>287 missing</td>
              <td><button className="text-blue-600 hover:underline">Auto-fix from filename</button></td>
            </tr>
            <tr className="border-b">
              <td className="py-3"><span className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs">Error</span></td>
              <td>has_animal</td>
              <td>52 missing</td>
              <td><button className="text-blue-600 hover:underline">Re-run model</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Export Page
function ExportPage() {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold text-lg mb-4">Export Data</h3>
        
        <div className="grid grid-cols-3 gap-4 mb-6">
          <ExportOption icon="📊" title="Full Dataset" desc="All processed images with classifications" count="45,231 rows" />
          <ExportOption icon="🦊" title="Animals Only" desc="Images with detected animals" count="12,847 rows" />
          <ExportOption icon="⚠️" title="Needs Review" desc="Low confidence classifications" count="892 rows" />
        </div>

        <div className="border-t pt-4">
          <h4 className="font-medium mb-3">Filters</h4>
          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="text-sm text-gray-600">Start Date</label>
              <input type="date" defaultValue="2024-01-01" className="w-full border rounded p-2 mt-1" lang="en" />
            </div>
            <div>
              <label className="text-sm text-gray-600">End Date</label>
              <input type="date" defaultValue="2024-12-31" className="w-full border rounded p-2 mt-1" lang="en" />
            </div>
            <div>
              <label className="text-sm text-gray-600">Camera</label>
              <select className="w-full border rounded p-2 mt-1">
                <option>All Cameras</option>
                <option>Research Park</option>
                <option>San Joaquin Marsh</option>
                <option>Ecological Reserve</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-600">Species</label>
              <select className="w-full border rounded p-2 mt-1">
                <option>All Species</option>
                <option>Coyote</option>
                <option>Rabbit</option>
                <option>Deer</option>
                <option>Bird</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-4 gap-4 mt-4">
            <div>
              <label className="text-sm text-gray-600">Min Confidence (%)</label>
              <input type="number" defaultValue="50" min="0" max="100" className="w-full border rounded p-2 mt-1" />
            </div>
            <div>
              <label className="text-sm text-gray-600">Classification Status</label>
              <select className="w-full border rounded p-2 mt-1">
                <option>All</option>
                <option>Confirmed</option>
                <option>Pending Review</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Export Format</h3>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 p-4 border rounded-lg cursor-pointer hover:bg-gray-50 border-blue-400 bg-blue-50">
            <input type="radio" name="format" defaultChecked className="text-blue-600" />
            <span className="font-medium">CSV</span>
          </label>
          <label className="flex items-center gap-2 p-4 border rounded-lg cursor-pointer hover:bg-gray-50">
            <input type="radio" name="format" />
            <span>Excel (.xlsx)</span>
          </label>
          <label className="flex items-center gap-2 p-4 border rounded-lg cursor-pointer hover:bg-gray-50">
            <input type="radio" name="format" />
            <span>JSON</span>
          </label>
        </div>

        <button className="mt-6 w-full py-3 rounded-lg text-white font-medium transition hover:opacity-90" style={{ backgroundColor: colors.uciBlue }}>
          📥 Download Export
        </button>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="font-semibold mb-4">Export History</h3>
        <table className="w-full text-sm">
          <thead className="text-left text-gray-500 border-b">
            <tr>
              <th className="pb-2">Date</th>
              <th className="pb-2">Type</th>
              <th className="pb-2">Records</th>
              <th className="pb-2">Format</th>
              <th className="pb-2">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b">
              <td className="py-3">Feb 10, 2026</td>
              <td>Full Dataset</td>
              <td>45,231</td>
              <td>CSV</td>
              <td><button className="text-blue-600 hover:underline">Re-download</button></td>
            </tr>
            <tr className="border-b">
              <td className="py-3">Feb 5, 2026</td>
              <td>Animals Only</td>
              <td>12,500</td>
              <td>Excel</td>
              <td><button className="text-blue-600 hover:underline">Re-download</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Helper Components
function ActivityItem({ time, action, detail, status }) {
  const statusColors = {
    success: 'bg-green-100 text-green-700',
    warning: 'bg-yellow-100 text-yellow-700',
    error: 'bg-red-100 text-red-700',
  };
  return (
    <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
      <span className={`px-2 py-1 rounded text-xs font-medium ${statusColors[status]}`}>{action}</span>
      <span className="flex-1 text-sm">{detail}</span>
      <span className="text-xs text-gray-400">{time}</span>
    </div>
  );
}

function ValidationCard({ title, value, status }) {
  const statusColors = {
    info: 'border-blue-200 bg-blue-50',
    success: 'border-green-200 bg-green-50',
    warning: 'border-yellow-200 bg-yellow-50',
    error: 'border-red-200 bg-red-50',
  };
  return (
    <div className={`p-4 rounded-lg border-2 ${statusColors[status]}`}>
      <div className="text-sm text-gray-600">{title}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function CheckItem({ label, status, detail }) {
  const statusIcons = {
    pass: { icon: '✓', color: 'text-green-500' },
    warning: { icon: '⚠', color: 'text-yellow-500' },
    error: { icon: '✗', color: 'text-red-500' },
  };
  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
      <div className="flex items-center gap-3">
        <span className={statusIcons[status].color}>{statusIcons[status].icon}</span>
        <span>{label}</span>
      </div>
      <span className="text-sm text-gray-500">{detail}</span>
    </div>
  );
}

function ExportOption({ icon, title, desc, count }) {
  return (
    <div className="border rounded-lg p-4 hover:border-blue-400 cursor-pointer transition hover:bg-blue-50">
      <div className="text-3xl mb-2">{icon}</div>
      <div className="font-medium">{title}</div>
      <div className="text-sm text-gray-500">{desc}</div>
      <div className="text-sm text-blue-600 mt-2 font-medium">{count}</div>
    </div>
  );
}
