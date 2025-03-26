import { useState } from 'react';
import { useRouter } from 'next/router';

const CommentRating = ({ orderId, currentUser }) => {
  const router = useRouter();
  const [commentText, setCommentText] = useState('');
  const [rating, setRating] = useState(0);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmitRating = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError('');

    // Validation
    if (!commentText.trim()) {
      setError('Please enter a comment');
      setIsSubmitting(false);
      return;
    }

    if (rating === 0) {
      setError('Please select a rating');
      setIsSubmitting(false);
      return;
    }

    try {
      const response = await fetch('/api/comments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          orderId,
          comment: commentText.trim(),
          rating,
          userId: currentUser?.id,
          createdAt: new Date(),
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.message || 'Failed to save comment');
      }

      // Redirect to home page after successful submission
      router.push('/');
    } catch (error) {
      console.error('Error saving comment:', error);
      setError(error.message || 'Failed to save your comment. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmitRating} className="comment-rating-form">
      <div className="rating-section">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => setRating(star)}
            className={`star-button ${rating >= star ? 'active' : ''}`}
          >
            ★
          </button>
        ))}
      </div>

      <textarea
        value={commentText}
        onChange={(e) => setCommentText(e.target.value)}
        placeholder="Write your comment here..."
        required
      />

      {error && <div className="error-message">{error}</div>}

      <button 
        type="submit" 
        disabled={isSubmitting}
        className="submit-button"
      >
        {isSubmitting ? 'Submitting...' : 'Submit Rating'}
      </button>
    </form>
  );
};

export default CommentRating; 