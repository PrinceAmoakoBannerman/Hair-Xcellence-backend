// Product photos in the admin: show what was picked before the form is saved.
(function () {
  const root = document.currentScript && document.currentScript.closest('.hx-photos')
  if (!root) return

  // "Add photos": thumbnails of the chosen files.
  const add = root.querySelector('[data-hx-add]')
  const pending = root.querySelector('[data-hx-pending]')
  if (add && pending) {
    add.addEventListener('change', () => {
      pending.replaceChildren()
      const files = Array.from(add.files || [])
      pending.hidden = files.length === 0
      if (!files.length) return
      const note = document.createElement('p')
      note.textContent = files.length + (files.length === 1 ? ' photo' : ' photos') + ' ready to add. Click Save to upload.'
      pending.append(note)
      files.forEach(file => {
        const img = document.createElement('img')
        img.alt = ''
        img.src = URL.createObjectURL(file)
        pending.append(img)
      })
    })
  }

  // "Replace": show the new photo in the card straight away.
  root.querySelectorAll('.hx-photo-replace input[type=file]').forEach(input => {
    input.addEventListener('change', () => {
      const file = input.files && input.files[0]
      const card = input.closest('.hx-photo')
      if (!file || !card) return
      const old = card.querySelector('[data-hx-preview]')
      const img = document.createElement('img')
      img.alt = ''
      img.src = URL.createObjectURL(file)
      img.setAttribute('data-hx-preview', '')
      old.replaceWith(img)
      card.classList.add('is-replaced')
      input.closest('label').querySelector('span').textContent = 'New photo chosen'
    })
  })
})()
