export function requestForDelivery(request, delivery) {
  if (delivery === 'embedded_data_url') return request;
  if (request.input.images) {
    return {...request,
      task: request.task + ' ALL source images are separately attached using the filenames in input.images. Inspect every attachment in the given order; report missing/unreadable attachments without guessing.',
      input: {...request.input, images: request.input.images.map(({data_url, ...image}) => ({...image, delivery: 'separate_attachment'}))},
    };
  }
  const {data_url, ...image} = request.input.image;
  return {
    ...request,
    task: request.task + ' The source image is separately attached as reference.webp. Inspect that attachment; do not guess if it is missing or unreadable.',
    input: {...request.input, image: {...image, delivery: 'separate_attachment'}},
  };
}

export const requestImages = request => request ? (request.input.images || [request.input.image]) : [];
