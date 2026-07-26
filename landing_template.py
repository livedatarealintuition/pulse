LANDING_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <title>Pulse — Investment Portfolio Tracker</title>
    <link rel="icon" href="/pulse_logo.png" type="image/png">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #020617; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; }
        .container { max-width: 1100px; margin: 0 auto; padding: 40px 20px; }
        .hero { text-align: center; padding: 80px 20px 60px; }
        .hero h1 { font-size: 4rem; font-weight: 900; background: linear-gradient(135deg, #34d399, #22d3ee); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .hero p { color: #94a3b8; font-size: 1.2rem; margin-top: 16px; }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 24px; margin: 60px 0; }
        .feature-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 28px 24px; text-align: center; }
        .feature-card .icon { font-size: 2.5rem; margin-bottom: 12px; }
        .feature-card h3 { font-size: 1.1rem; font-weight: 700; color: #34d399; margin-bottom: 8px; }
        .feature-card p { color: #64748b; font-size: 0.9rem; line-height: 1.5; }
        .pricing { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; margin: 60px 0; }
        .pricing-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px 28px; text-align: center; }
        .pricing-card.pro { border-color: #22d3ee; background: linear-gradient(135deg, #0f172a, #0c1929); }
        .pricing-card h3 { font-size: 1.3rem; font-weight: 800; margin-bottom: 8px; }
        .pricing-card .price { font-size: 2.5rem; font-weight: 900; color: #22d3ee; margin: 16px 0; }
        .pricing-card .price span { font-size: 1rem; color: #64748b; }
        .pricing-card ul { list-style: none; text-align: left; margin: 20px 0; color: #94a3b8; font-size: 0.9rem; line-height: 2; }
        .pricing-card ul li::before { content: "✓ "; color: #34d399; font-weight: bold; }
        .btn { display: inline-block; padding: 12px 32px; border-radius: 12px; font-weight: 700; font-size: 1rem; cursor: pointer; border: none; transition: all 0.2s; text-decoration: none; }
        .btn-primary { background: linear-gradient(135deg, #34d399, #22d3ee); color: #020617; }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(34, 211, 238, 0.3); }
        .btn-outline { background: transparent; border: 2px solid #22d3ee; color: #22d3ee; }
        .btn-outline:hover { background: rgba(34, 211, 238, 0.1); }
        .auth-section { text-align: center; padding: 40px 0 20px; }
        .auth-section h2 { font-size: 1.5rem; margin-bottom: 20px; }
        .auth-form { display: flex; flex-direction: column; gap: 12px; max-width: 360px; margin: 0 auto; }
        .auth-form input { padding: 12px 16px; border-radius: 10px; border: 1px solid #1e293b; background: #0f172a; color: #e2e8f0; font-size: 1rem; }
        .auth-form input:focus { outline: none; border-color: #22d3ee; }
        .auth-form button { margin-top: 8px; }
        .footer { text-align: center; padding: 60px 20px 20px; color: #475569; font-size: 0.8rem; }
        .divider { display: flex; align-items: center; gap: 16px; margin: 20px 0; color: #475569; font-size: 0.85rem; }
        .divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: #1e293b; }
        #auth-message { color: #f87171; font-size: 0.85rem; margin-top: 8px; display: none; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>Pulse</h1>
            <p>Live Data · Real Intuition — Track your portfolio across US, HK, CN, TW markets</p>
        </div>

        <div class="features">
            <div class="feature-card">
                <div class="icon">📊</div>
                <h3>Multi-Market</h3>
                <p>Track US, HK, CN, and TW stocks in one unified dashboard with real-time prices.</p>
            </div>
            <div class="feature-card">
                <div class="icon">🤖</div>
                <h3>AI Analysis</h3>
                <p>Get AI-powered portfolio audit reports with risk assessment and recommendations.</p>
            </div>
            <div class="feature-card">
                <div class="icon">📈</div>
                <h3>Live Tracking</h3>
                <p>Real-time price updates, P&L calculation, stop-loss alerts, and target price monitoring.</p>
            </div>
            <div class="feature-card">
                <div class="icon">🔍</div>
                <h3>Smart Watchlist</h3>
                <p>Organized watchlists with drag-and-drop, target prices, and instant price checking.</p>
            </div>
            <div class="feature-card">
                <div class="icon">🌍</div>
                <h3>Multi-Currency</h3>
                <p>View in USD, HKD, TWD, CNY, JPY, EUR, or GBP with live forex rates.</p>
            </div>
        </div>

        <div class="pricing">
            <div class="pricing-card">
                <h3>Free</h3>
                <div class="price">$0<span>/month</span></div>
                <ul>
                    <li>Unlimited portfolio tracking</li>
                    <li>Real-time price data</li>
                    <li>Multi-market support</li>
                    <li>Watchlist management</li>
                    <li>Basic analytics</li>
                </ul>
            </div>
            <div class="pricing-card pro">
                <h3>Pro</h3>
                <div class="price">$5<span>/month</span></div>
                <ul>
                    <li>Everything in Free</li>
                    <li>AI portfolio audit reports</li>
                    <li>Advanced analytics & charts</li>
                    <li>Target price alerts</li>
                    <li>Custom AI model configuration</li>
                    <li>Priority background updates</li>
                </ul>
            </div>
        </div>

        <div class="auth-section">
            <h2>Get Started</h2>
            <div class="auth-form" id="auth-form">
                <button class="btn btn-outline" onclick="signInWithGoogle()">Sign in with Google</button>
                <div class="divider">or</div>
                <input type="email" id="auth-email" placeholder="Email address">
                <input type="password" id="auth-password" placeholder="Password">
                <button class="btn btn-primary" onclick="signInWithEmail()">Continue</button>
                <div id="auth-message"></div>
            </div>
        </div>

        <div class="footer">
            <p>Pulse v{{ version }} — Self-host your own data or use Pulse Cloud.</p>
            <p><a href="https://github.com/nousresearch/pulse" style="color:#22d3ee;">View on GitHub</a></p>
        </div>
    </div>

    <script>
        const supabaseClient = supabase.createClient("{{ supabase_url }}", "{{ supabase_key }}");
        function setCookie(name, value) {
            document.cookie = name + "=" + value + ";path=/;max-age=86400;SameSite=Lax";
        }
        function showMessage(msg, isError) {
            const el = document.getElementById("auth-message");
            el.textContent = msg;
            el.style.color = isError ? "#f87171" : "#34d399";
            el.style.display = "block";
        }
        function redirectToDashboard() { window.location.href = "/dashboard"; }
        async function signInWithGoogle() {
            const { data, error } = await supabaseClient.auth.signInWithOAuth({
                provider: "google",
                options: { redirectTo: window.location.origin + "/dashboard" }
            });
            if (error) showMessage(error.message, true);
        }
        async function signInWithEmail() {
            const email = document.getElementById("auth-email").value;
            const password = document.getElementById("auth-password").value;
            if (!email || !password) { showMessage("Please enter email and password", true); return; }
            const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
            if (error) {
                if (error.message.includes("Invalid login")) {
                    const { data: signUpData, error: signUpError } = await supabaseClient.auth.signUp({ email, password });
                    if (signUpError) { showMessage(signUpError.message, true); return; }
                    showMessage("Account created! Check your email to confirm.", false);
                    return;
                }
                showMessage(error.message, true);
                return;
            }
            if (data.session) {
                setCookie("sb-access-token", data.session.access_token);
                redirectToDashboard();
            }
        }
        supabaseClient.auth.onAuthStateChange((event, session) => {
            if (event === "SIGNED_IN" && session) {
                setCookie("sb-access-token", session.access_token);
                redirectToDashboard();
            }
        });
    </script>
</body>
</html>
"""
