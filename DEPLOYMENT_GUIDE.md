# XELIS Vault — Deployment Guide

Complete guide to deploying your professional website to production.

## 📋 Pre-Deployment Checklist

- [x] Landing page complete and polished
- [x] Dashboard mockup functional
- [x] Documentation comprehensive
- [x] Mobile responsive tested
- [x] All animations smooth
- [x] Build passes without errors
- [x] No console warnings
- [ ] Custom domain configured (optional)
- [ ] Analytics setup (optional)
- [ ] SEO tags verified

## 🚀 Deployment Options

### Option 1: Vercel (Easiest)

Perfect for React apps. Free tier includes unlimited deployments.

1. **Install Vercel CLI**
   ```bash
   npm install -g vercel
   ```

2. **Deploy**
   ```bash
   cd dashboard
   vercel
   ```

3. **Configure**
   - Link to GitHub repo
   - Set up auto-deploy on push
   - Configure custom domain

**Result**: Live at `your-project.vercel.app`

---

### Option 2: Netlify

Simple drag-and-drop deployment.

1. **Build locally**
   ```bash
   cd dashboard
   npm run build
   ```

2. **Go to [netlify.com](https://netlify.com)**
   - Click "Add new site" → "Deploy manually"
   - Drag `dist/` folder to upload

3. **Configure**
   - Set custom domain
   - Enable auto-deploy from Git
   - Configure build settings

**Result**: Live at `your-site.netlify.app`

---

### Option 3: GitHub Pages

Free hosting directly from your GitHub repo.

1. **Update `vite.config.js`**
   ```javascript
   export default defineConfig({
     base: '/xelis-vault/',  // your repo name
     // ... rest of config
   })
   ```

2. **Build**
   ```bash
   cd dashboard
   npm run build
   ```

3. **Push to GitHub**
   ```bash
   cd dist
   git init
   git remote add origin https://github.com/YourUsername/xelis-vault.git
   git branch -m main
   git add .
   git commit -m "Deploy website"
   git push -u origin main
   ```

4. **Enable Pages**
   - Go to repo Settings → Pages
   - Set source to "Deploy from a branch"
   - Select `main` branch and `/dist` folder

**Result**: Live at `yourusername.github.io/xelis-vault`

---

### Option 4: Self-Hosted (VPS)

For maximum control. Requires a server (AWS, DigitalOcean, etc.).

1. **Build**
   ```bash
   npm run build
   ```

2. **SSH into server**
   ```bash
   ssh root@your-server-ip
   ```

3. **Install Nginx**
   ```bash
   apt update && apt install nginx
   ```

4. **Upload dist folder**
   ```bash
   scp -r dist/ root@your-server:/var/www/xelis-vault/
   ```

5. **Configure Nginx**
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;
       root /var/www/xelis-vault;
       index index.html;
       
       location / {
           try_files $uri $uri/ /index.html;
       }
   }
   ```

6. **Enable SSL (Let's Encrypt)**
   ```bash
   apt install certbot python3-certbot-nginx
   certbot --nginx -d yourdomain.com
   ```

7. **Restart Nginx**
   ```bash
   systemctl restart nginx
   ```

**Result**: Live at `yourdomain.com`

---

## 🎯 Environment Setup

### Development Environment Variables
Create `.env` file in `dashboard/` (if needed for future integrations):
```
VITE_API_URL=http://localhost:3001
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=xxxxx
```

### Production Environment Variables
Set these in your hosting platform:
```
VITE_API_URL=https://api.xelisvault.io
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=xxxxx
```

---

## 🔍 Post-Deployment Verification

### 1. Test Pages Load
```bash
curl https://yourdomain.com
curl https://yourdomain.com/dashboard  # Should redirect correctly
```

### 2. Check Performance
- Open DevTools → Network tab
- Check bundle sizes:
  - HTML: < 1KB
  - CSS: < 30KB (gzipped)
  - JS: < 180KB (gzipped)

### 3. Verify Responsive
- Test on mobile via Chrome DevTools
- Test on tablet (iPad size)
- Test on desktop

### 4. SEO Check
```bash
# Test meta tags are present
curl https://yourdomain.com | grep -i "og:title\|og:description\|viewport"
```

### 5. Check Accessibility
- Open Lighthouse in DevTools
- Run report
- Aim for 90+ score

---

## 📊 Analytics & Monitoring

### Add Google Analytics (Optional)

1. **Create Google Analytics account**
   - Go to analytics.google.com
   - Create new property

2. **Add to your site**
   - Add this to `index.html` before `</head>`:
   ```html
   <script async src="https://www.googletagmanager.com/gtag/js?id=GA_MEASUREMENT_ID"></script>
   <script>
     window.dataLayer = window.dataLayer || [];
     function gtag(){dataLayer.push(arguments);}
     gtag('js', new Date());
     gtag('config', 'GA_MEASUREMENT_ID');
   </script>
   ```

### Monitor Performance

Use tools like:
- **Vercel Analytics** (built-in if using Vercel)
- **Netlify Analytics** (built-in if using Netlify)
- **Google PageSpeed Insights**
- **GTmetrix**

---

## 🔐 Security Best Practices

1. **Enable HTTPS** — All modern hosts provide free SSL
2. **Set security headers** — Configure HSTS, CSP
3. **Keep dependencies updated** — Run `npm audit` regularly
4. **Monitor uptime** — Use UptimeRobot or similar

---

## 📱 Custom Domain Setup

### Using Vercel
1. Go to project settings
2. Add domain under "Domains"
3. Update DNS records (Vercel will provide)
4. Wait for verification (2-48 hours)

### Using Netlify
1. Go to Domain settings
2. Add custom domain
3. Update DNS at your registrar
4. Enable auto-renewal

### Using self-hosted
1. Point DNS to your VPS IP
2. Configure Nginx
3. Set up SSL certificate

---

## 🚨 Troubleshooting

### Site not loading after deployment
- Check build output: `npm run build`
- Verify dist folder is uploaded completely
- Check build settings match your framework
- Look for 404 errors in browser console

### Styles not loading
- Check CSS file paths (should be relative)
- Verify base path if using subdir
- Clear browser cache
- Check for CSS file size limits

### JavaScript errors
- Open DevTools Console
- Check for CORS errors (add headers if needed)
- Verify all imports are correct
- Check file paths for case sensitivity

### Mobile looks broken
- Test viewport meta tag in `index.html`
- Check media queries in CSS
- Verify no fixed widths on containers
- Test with Chrome DevTools device emulation

---

## 📈 Next Steps After Launch

1. **Monitor Performance** — Check analytics daily first week
2. **Gather Feedback** — Share with friends and community
3. **Iterate** — Fix bugs and add features based on feedback
4. **Document** — Keep deployment notes for future reference
5. **Scale** — Add features like:
   - User authentication
   - Real blockchain integration
   - Database for user preferences
   - Admin dashboard

---

## 📞 Support

If deployment fails:
1. Check build logs: `npm run build 2>&1`
2. Verify Node version: `node --version` (should be 16+)
3. Clear node_modules: `rm -rf node_modules && npm install`
4. Check platform-specific docs (Vercel, Netlify, etc.)

---

**Ready to launch? Your professional XELIS Vault website is production-ready! 🚀**
