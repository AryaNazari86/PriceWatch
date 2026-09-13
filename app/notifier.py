"""Email notification when a watched product's price changes.
Isolated behind one function — notify_price_change() — so it's a clean
no-op stub if RESEND_API_KEY / NOTIFY_EMAIL aren't configured, and a
one-file swap if you'd rather use a different provider later.
Sending is best-effort: a failed or unconfigured email must never break a
price check. Callers should treat this as fire-and-forget.
"""

from __future__ import annotations
import logging
import resend
from . import config
from .models import Product

logger = logging.getLogger(__name__)
_configured = False

def _ensure_configured() -> bool:
    global _configured
    if not config.RESEND_API_KEY or not config.NOTIFY_EMAIL:
        return False
    if not _configured:
        resend.api_key = config.RESEND_API_KEY
        _configured = True
    return True

def notify_price_change(product: Product, old_price: float, new_price: float, direction: str) -> None:
    """Send a best-effort email about a detected price change. Never raises."""
    if not _ensure_configured():
        logger.info(
            "Skipping email for %s (%s -> %s): RESEND_API_KEY/NOTIFY_EMAIL not set",
            product.title or product.url,
            old_price,
            new_price,
        )
        return

    # 1. Determine dynamic copy based on drop vs increase
    is_drop = direction == "down"
    verb = "dropped" if is_drop else "went up"  
    arrow = "↓" if is_drop else "↑"  
    subject = f"{arrow} {product.title or product.url} price {verb}: {old_price} → {new_price}"  
    
    # 2. The "Timepiece" Color Palette
    bg = "#1C1A17"          # Onyx - page background
    surface = "#2A2723"     # Graphite - main email card
    surface_2 = "#3A352E"   # Raised surface - borders
    text = "#F4EFE6"        # Cream - primary text
    text_muted = "#A59B8A"  # Muted tan - old prices/footers
    accent = "#C8A552"      # Brass Gold - buttons
    drop_color = "#5F8D6A"  # Sage - price drop banner

    # 3. Dynamic Uniqlo-style banner mapping
    # Uses the Sage drop_color for drops, and surface_2 for increases
    banner_color = drop_color if is_drop else surface_2
    banner_title = "LUCKY YOU" if is_drop else "PRICE UPDATE"
    banner_text = "Good news! An item you liked just got a lower price." if is_drop else "An item you are watching has changed price."
    
    # 4. Public URLs for Images (REQUIRED FOR EMAILS)
    # TODO: Update this to your active ngrok URL before the demo!
    public_base_url = "https://YOUR-NGROK-URL.ngrok-free.app" 
    
    # Pointing to the images in your static folder
    logo_url = f"{public_base_url}/static/image_a9cef0.jpg"
    product_image_url = f"{public_base_url}/static/image_9f70ef.jpg" 

    # 5. The HTML Template (Inline CSS required for email clients)
    html = f"""  
    <div style="background-color: {bg}; padding: 40px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; text-align: center; width: 100%;">
      
      <!-- Logo Header -->
      <div style="margin-bottom: 30px;">
        <img src="{logo_url}" alt="PriceWatch Logo" width="80" style="display: block; margin: 0 auto;">
      </div>

      <!-- Main Card Container -->
      <div style="max-width: 600px; margin: 0 auto; background-color: {surface}; overflow: hidden; border: 1px solid {surface_2};">
        
        <!-- Colored Banner Section (Mimics the red Uniqlo banner) -->
        <div style="background-color: {banner_color}; padding: 40px 20px 90px 20px; color: {text};">
          <h1 style="margin: 0; font-size: 28px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;">
            {banner_title}
          </h1>
          <p style="margin: 10px 0 0 0; font-size: 16px; color: {text};">
            {banner_text}
          </p>
        </div>

        <!-- Product Box (Overlaps the banner slightly) -->
        <div style="background-color: {bg}; margin: -60px 40px 40px 40px; padding: 30px; border: 1px solid {surface_2}; box-shadow: 0 10px 20px rgba(0,0,0,0.3);">
          
          <img src="{product_image_url}" alt="Product Image" style="width: 100%; max-width: 200px; height: auto; margin-bottom: 20px; border: 1px solid {surface_2};">
          
          <h2 style="margin: 0 0 10px 0; font-size: 14px; color: {text}; text-transform: uppercase; letter-spacing: 1px; line-height: 1.4;">
            {product.title or product.url}
          </h2>
          
          <!-- Price Display -->
          <p style="font-size: 24px; margin: 15px 0; color: {text}; font-weight: bold;">
            <span style="text-decoration: line-through; color: {text_muted}; font-size: 18px; font-weight: normal; margin-right: 10px;">{product.currency} {old_price}</span> 
            {product.currency} {new_price}
          </p>

          <!-- Shop Now Button -->
          <a href="{product.url}" style="display: inline-block; background-color: {accent}; color: #000000; text-decoration: none; padding: 14px 36px; font-size: 14px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; margin-top: 15px;">
            Shop Now
          </a>
        </div>

      </div>
      
      <p style="color: {text_muted}; font-size: 12px; margin-top: 25px; text-transform: uppercase; letter-spacing: 0.05em;">
        PriceWatch Automated Alert
      </p>
    </div>
    """

    try:  
        resend.Emails.send(  
            {  
                "from": config.RESEND_FROM_EMAIL,  
                "to": [config.NOTIFY_EMAIL],  
                "subject": subject,  
                "html": html,  
            }  
        )  
        logger.info("Sent price-change email for %s", product.title or product.url)  
    except Exception:  
        logger.exception("Failed to send price-change email for %s", product.title or product.url)