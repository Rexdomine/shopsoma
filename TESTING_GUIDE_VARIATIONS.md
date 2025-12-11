# Product Variations - Quick Testing Guide

**Date**: December 9, 2025
**Status**: Ready for Testing

---

## START TESTING

### 1. Start the Development Server

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-frontend
npm run dev
```

Open browser to: `http://localhost:5173`

### 2. Login as Vendor

Navigate to vendor login and use your vendor credentials.

### 3. Navigate to Add Product

Click "Products" → "Add New Product"

---

## QUICK TEST SCENARIOS

### Scenario 1: Image Upload (2 minutes)

**Steps**:
1. Scroll to "Other Details" section
2. Toggle "Product Variations" ON
3. Click "Add Variation" button
4. Scroll to "Upload Images" section
5. Click upload button
6. Select 2-3 images (JPG/PNG)
7. Watch progress indicator
8. Verify checkmarks appear
9. Hover over image → Click X to delete

**✅ Pass Criteria**:
- Progress bar shows during upload
- Green checkmarks on uploaded images
- Delete button appears on hover
- Images removed when X clicked

---

### Scenario 2: Size Selection (1 minute)

**Steps**:
1. Add Variation → Enter name "Test Red"
2. Select type "Color"
3. Click sizes: XL, L, M (should turn green)
4. Click "Save Variation"
5. Click Edit button on saved variation
6. Check which sizes are highlighted

**✅ Pass Criteria**:
- Size buttons turn green when clicked
- Clicking again turns them gray (toggle)
- Edit modal shows correct sizes as green
- Can toggle sizes in edit mode

---

### Scenario 3: Color Sync (1 minute)

**Steps**:
1. Add Variation
2. Click color picker → Select RED
3. Look at hex input (should say #FF0000 or similar)
4. Type "#0000FF" in hex input
5. Look at color picker (should turn BLUE)
6. Type "#GGGGGG" in hex input
7. Color picker should stay at last valid color

**✅ Pass Criteria**:
- Color picker updates hex input
- Valid hex updates color picker
- Invalid hex doesn't break picker
- Both stay synced

---

### Scenario 4: Validation (2 minutes)

Try these deliberately wrong actions:

**Test A**: Leave name empty → Click Save
- ✅ Should show: "Variation name is required"

**Test B**: Leave type empty → Click Save
- ✅ Should show: "Please select a variation type"

**Test C**: Don't select any sizes → Click Save
- ✅ Should show: "Please select at least one size"

**Test D**: Select size, enter stock: "-5" → Click Save
- ✅ Should show: "Invalid stock value for size..."

**Test E**: Check "Different Pricing", enter price "abc" → Click Save
- ✅ Should show: "Invalid variation price"

**All should show warning toast and NOT save variation**

---

### Scenario 5: Complete Flow (3 minutes)

**Full Happy Path**:

1. Fill product basic info:
   - Name: "Test Product"
   - Price: $50
   - Category: Any category
   - Description: "Test description"

2. Upload 1-2 main product images

3. Toggle "Product Variations" ON

4. Click "Add Variation"

5. Fill variation form:
   - Name: "Black XL"
   - Type: "Color"
   - Check "Different Pricing"
   - Price: $59.99
   - Sales Price: $49.99
   - Color: Black (#000000)
   - Click sizes: XL, L
   - Stock: XL=10, L=15
   - Upload 1 variation image

6. Click "Save Variation"
   - ✅ Should show success toast
   - ✅ Variation appears in list

7. Click Edit on saved variation
   - ✅ All fields populated correctly
   - ✅ XL and L buttons are green

8. Change name to "Black XL Premium"
9. Click "Update Variation"
   - ✅ Should show "Variation updated successfully"

10. Click "Publish for Review"
    - ✅ Product should submit
    - ✅ Check browser console for variations in payload

---

## EXPECTED BEHAVIOR

### Image Upload
- Upload button opens file picker
- Progress shown as percentage
- Green checkmarks on success
- Red X to delete images
- Toast on completion

### Size Selection
- Buttons toggle green/gray
- Edit shows previous selections highlighted
- Can select multiple sizes

### Color Sync
- Both inputs always match (when valid)
- Instant updates
- Invalid hex doesn't crash

### Validation
- Clear error messages
- Modal stays open on error
- No variation saved if invalid

### Overall Flow
- Smooth form interactions
- Fast state updates
- No console errors
- Success toasts visible
- Data persists through edit

---

## IF SOMETHING BREAKS

### Check Browser Console

Open DevTools (F12) → Console tab

Look for:
- ❌ Red errors
- ⚠️ Yellow warnings
- Network failed requests

### Common Issues

**"Cannot read property of undefined"**
- Refresh page and try again
- Check if backend is running

**"Failed to fetch"**
- Backend not running
- Check `http://localhost:8000`

**"Image upload failed"**
- Check backend logs
- Verify R2 credentials in .env

**TypeScript errors in terminal**
- Restart dev server
- Run `npx tsc --noEmit` to check

---

## REPORT BUGS

If you find issues, note:

1. **What you did** (exact steps)
2. **What happened** (actual behavior)
3. **What you expected** (expected behavior)
4. **Browser console errors** (if any)
5. **Screenshots** (if helpful)

---

## SUCCESS CRITERIA

Feature is working if:

- ✅ Can upload variation images
- ✅ Images show with checkmarks
- ✅ Can delete images
- ✅ Size buttons highlight on click
- ✅ Edit shows correct sizes highlighted
- ✅ Color picker and hex stay synced
- ✅ Invalid data shows warnings
- ✅ Valid data saves successfully
- ✅ Edit loads all data correctly
- ✅ Update saves changes
- ✅ Product submits with variations

---

## QUICK COMMAND REFERENCE

```bash
# Start frontend
cd shopsoma-frontend && npm run dev

# Start backend (if needed)
cd shopsoma-backend && source venv/bin/activate && uvicorn app.main:app --reload

# TypeScript check
cd shopsoma-frontend && npx tsc --noEmit

# View backend logs
# Terminal where backend is running
```

---

**Testing Time**: ~10 minutes for all scenarios
**Priority**: Test Scenarios 1-4 first (core fixes)
**Status**: Ready to test immediately
