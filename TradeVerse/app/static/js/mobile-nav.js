// Mobile Navigation Toggle
document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileNavDrawer = document.getElementById('mobileNavDrawer');
    const mobileNavOverlay = document.getElementById('mobileNavOverlay');
    const mobileNavClose = document.getElementById('mobileNavClose');
    
    // Only proceed if mobile navigation elements exist
    if (!mobileMenuBtn || !mobileNavDrawer) {
        return;
    }
    
    // Open mobile menu
    function openMobileNav() {
        mobileNavDrawer.classList.add('active');
        if (mobileNavOverlay) {
            mobileNavOverlay.classList.add('active');
        }
        document.body.style.overflow = 'hidden';
    }
    
    // Close mobile menu
    function closeMobileNav() {
        mobileNavDrawer.classList.remove('active');
        if (mobileNavOverlay) {
            mobileNavOverlay.classList.remove('active');
        }
        document.body.style.overflow = '';
    }
    
    // Toggle mobile menu
    function toggleMobileNav() {
        if (mobileNavDrawer.classList.contains('active')) {
            closeMobileNav();
        } else {
            openMobileNav();
        }
    }
    
    // Event listeners
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', toggleMobileNav);
    }
    
    if (mobileNavClose) {
        mobileNavClose.addEventListener('click', closeMobileNav);
    }
    
    if (mobileNavOverlay) {
        mobileNavOverlay.addEventListener('click', closeMobileNav);
    }
    
    // Close on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && mobileNavDrawer.classList.contains('active')) {
            closeMobileNav();
        }
    });
    
    // Close menu when clicking a nav link (for better UX)
    const navLinks = mobileNavDrawer ? mobileNavDrawer.querySelectorAll('.nav-link') : [];
    navLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            // Small delay to allow navigation to start
            setTimeout(closeMobileNav, 150);
        });
    });
});

