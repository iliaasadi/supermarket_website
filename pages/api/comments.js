import { prisma } from '../../lib/prisma'; // Adjust based on your DB setup

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ message: 'Method not allowed' });
  }

  try {
    const { 
      orderId, 
      food_quality,
      delivery_service,
      packaging,
      value_for_money,
      overall_experience,
      comment 
    } = req.body;

    // Validation
    if (!orderId || !food_quality || !delivery_service || !packaging || !value_for_money || !overall_experience) {
      return res.status(400).json({ message: 'Missing required fields' });
    }

    // First, check if the order exists
    const order = await prisma.order.findUnique({
      where: { id: orderId }
    });

    if (!order) {
      return res.status(404).json({ message: 'Order not found' });
    }

    // Save to database with order relationship
    const newComment = await prisma.comment.create({
      data: {
        orderId,
        food_quality: parseInt(food_quality),
        delivery_service: parseInt(delivery_service),
        packaging: parseInt(packaging),
        value_for_money: parseInt(value_for_money),
        overall_experience: parseInt(overall_experience),
        comment: comment || '',
        createdAt: new Date(),
        order: {
          connect: { id: orderId } // This ensures the comment is linked to the order
        }
      },
    });

    return res.status(200).json(newComment);
  } catch (error) {
    console.error('API Error:', error);
    return res.status(500).json({ message: 'Internal server error' });
  }
} 