import { useState } from 'react';
import { useRouter } from 'next/router';

export default function OrderPage({ order }) {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [ratings, setRatings] = useState({
    food_quality: 0,
    delivery_service: 0,
    packaging: 0,
    value_for_money: 0,
    overall_experience: 0
  });
  const [comment, setComment] = useState('');

  const handleRatingChange = (field, value) => {
    setRatings(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const response = await fetch('/api/comments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          orderId: order.id,
          ...ratings,
          comment
        })
      });

      if (!response.ok) {
        throw new Error('Failed to submit rating');
      }

      // Show success message
      alert('Rating submitted successfully!');
      
      // Redirect to home page
      router.push('/');
    } catch (error) {
      console.error('Error:', error);
      alert('Error submitting rating');
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderStarRating = (field) => {
    return (
      <div className="rating-input">
        {[5, 4, 3, 2, 1].map((star) => (
          <label key={star}>
            <input
              type="radio"
              name={field}
              value={star}
              checked={ratings[field] === star}
              onChange={() => handleRatingChange(field, star)}
              required
            />
            <i className={`fas fa-star ${ratings[field] >= star ? 'text-warning' : ''}`}></i>
          </label>
        ))}
      </div>
    );
  };

  return (
    <div className="card shadow-sm" id="ratingCard">
      <div className="card-header bg-light">
        <h5 className="card-title mb-0">Rate Your Order</h5>
      </div>
      <div className="card-body">
        <form onSubmit={handleSubmit}>
          <div className="row">
            <div className="col-md-6">
              <div className="mb-3">
                <label className="form-label">Food Quality</label>
                {renderStarRating('food_quality')}
              </div>
              <div className="mb-3">
                <label className="form-label">Delivery Service</label>
                {renderStarRating('delivery_service')}
              </div>
              <div className="mb-3">
                <label className="form-label">Packaging</label>
                {renderStarRating('packaging')}
              </div>
            </div>
            <div className="col-md-6">
              <div className="mb-3">
                <label className="form-label">Value for Money</label>
                {renderStarRating('value_for_money')}
              </div>
              <div className="mb-3">
                <label className="form-label">Overall Experience</label>
                {renderStarRating('overall_experience')}
              </div>
              <div className="mb-3">
                <label htmlFor="comment" className="form-label">Comment</label>
                <textarea
                  className="form-control"
                  id="comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows="3"
                />
              </div>
              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={isSubmitting || !Object.values(ratings).every(r => r > 0)}
              >
                {isSubmitting ? 'Submitting...' : 'Submit Rating'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
} 